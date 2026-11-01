"""The home page's cards: anyone reads them, the owner writes them -- as on the site's /home/edit/."""

from http import HTTPStatus

from django.utils.translation import gettext as _
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from accounts import roles
from api.auth import ApiTokenAuth
from api.schemas import LocalizedStr, LocalizedTitle, localize_field
from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
from home.models import HomeCard, blank_rich_text

auth = ApiTokenAuth()
router = Router(tags=["home"])

_LANGUAGES = ("ru", "kk", "en")


class HomeCardOut(Schema):
    id: int
    title: LocalizedStr
    body: LocalizedStr  # already-sanitized HTML
    position: int  # the cards are listed by it

    @staticmethod
    def resolve_title(obj: HomeCard) -> LocalizedStr:
        return localize_field(obj, "title")

    @staticmethod
    def resolve_body(obj: HomeCard) -> LocalizedStr:
        return localize_field(obj, "body")


class HomeCardIn(Schema):
    title: LocalizedTitle = LocalizedTitle()
    body: LocalizedStr = LocalizedStr()
    # Where to put the card, counted from 0; after the others when left out.
    position: int | None = Field(None, ge=0)


class HomeCardPatchIn(Schema):
    title: LocalizedTitle | None = None
    body: LocalizedStr | None = None
    position: int | None = Field(None, ge=0)


def _require_owner(user) -> None:
    # As on the site, where the edit page refuses everyone but the owner.
    if not roles.role_at_least(user, roles.EDIT_HOME_PAGE):
        raise HttpError(HTTPStatus.FORBIDDEN, "Owner role is required")


def _get_card_or_404(pk: int) -> HomeCard:
    try:
        return HomeCard.objects.get(pk=pk)
    except HomeCard.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found") from None


def _apply(card: HomeCard, payload: HomeCardIn | HomeCardPatchIn) -> None:
    if payload.title is not None:
        for lang in _LANGUAGES:
            setattr(card, f"title_{lang}", getattr(payload.title, lang).strip())
    if payload.body is not None:
        for lang in _LANGUAGES:
            body = getattr(payload.body, lang)
            if len(body) > MAX_RICH_TEXT_LENGTH:
                raise HttpError(
                    HTTPStatus.UNPROCESSABLE_CONTENT,
                    _("Body is too large (max %(limit)d characters).") % {"limit": MAX_RICH_TEXT_LENGTH},
                )
            setattr(card, f"body_{lang}", body)
    titles = [getattr(card, f"title_{lang}") for lang in _LANGUAGES]
    bodies = [getattr(card, f"body_{lang}") or "" for lang in _LANGUAGES]
    if not any(titles) and all(blank_rich_text(body) for body in bodies):
        raise HttpError(HTTPStatus.UNPROCESSABLE_CONTENT, _("A card needs a heading or some text."))


@router.get("/cards/", response=list[HomeCardOut], summary="List the home page's cards, in order")
def list_cards(request):
    return list(HomeCard.objects.all())


@router.post(
    "/cards/", response={HTTPStatus.CREATED: HomeCardOut}, auth=auth, summary="Add a card to the home page (owner)"
)
def create_card(request, payload: HomeCardIn):
    _require_owner(request.auth)
    card = HomeCard(position=HomeCard.next_position())
    _apply(card, payload)
    card.save()
    if payload.position is not None:
        card.place(payload.position)
    return Status(HTTPStatus.CREATED, card)


@router.patch("/cards/{pk}", response=HomeCardOut, auth=auth, summary="Change a card of the home page (owner)")
def update_card(request, pk: int, payload: HomeCardPatchIn):
    _require_owner(request.auth)
    card = _get_card_or_404(pk)
    _apply(card, payload)
    card.save()
    if payload.position is not None:
        card.place(payload.position)
    return card


@router.delete(
    "/cards/{pk}", response={HTTPStatus.NO_CONTENT: None}, auth=auth, summary="Remove a card from the home page (owner)"
)
def delete_card(request, pk: int):
    _require_owner(request.auth)
    _get_card_or_404(pk).delete()
    return Status(HTTPStatus.NO_CONTENT, None)
