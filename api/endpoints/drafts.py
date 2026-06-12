"""
News GET endpoints serve NewsArticle (officially published articles).
POST/PATCH/DELETE operate on DraftSubmission (community submission workflow).
Knowledge GET/write endpoints use DraftSubmission throughout.
"""

from datetime import datetime

from ninja import Router, Schema
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from api.schemas import LocalizedStr, localize_field
from knowledge.models import DraftSubmission
from news.models import NewsArticle

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()

news_router = Router(tags=["news"])
knowledge_router = Router(tags=["knowledge"])

_LOCALE_VALUES = ("ru", "kk", "en")


# -- Schemas ------------------------------------------------------------------


class DraftIn(Schema):
    title: str
    body: str
    locale: str
    category: str = ""


class DraftPatchIn(Schema):
    title: str | None = None
    body: str | None = None
    locale: str | None = None
    category: str | None = None


class DraftOut(Schema):
    id: int
    submission_type: str
    title: str
    body: str
    locale: str
    category: str
    status: str
    submitted_at: datetime
    author_id: int
    reviewer_note: str


class NewsArticleOut(Schema):
    id: int
    title: LocalizedStr
    intro: LocalizedStr
    body: LocalizedStr
    slug: str
    published_at: datetime
    is_hidden: bool
    published_by_id: int | None

    @staticmethod
    def resolve_title(obj: NewsArticle) -> LocalizedStr:
        return localize_field(obj, "title")

    @staticmethod
    def resolve_intro(obj: NewsArticle) -> LocalizedStr:
        return localize_field(obj, "intro")

    @staticmethod
    def resolve_body(obj: NewsArticle) -> LocalizedStr:
        return localize_field(obj, "body")


# -- Helpers ------------------------------------------------------------------


def _require_min_participant(user) -> None:
    if user.get_role_rank() < 1:
        raise HttpError(403, "Verified participant role or higher is required")


def _get_draft_or_404(pk: int, submission_type: str) -> DraftSubmission:
    try:
        return DraftSubmission.objects.get(pk=pk, submission_type=submission_type)
    except DraftSubmission.DoesNotExist:
        raise HttpError(404, "Draft not found") from None


def _require_owner_or_admin(user, draft: DraftSubmission) -> None:
    if draft.author_id != user.pk and not is_admin(user):
        raise HttpError(403, "Forbidden")


def _validate_locale(locale: str) -> None:
    if locale not in _LOCALE_VALUES:
        raise HttpError(422, f"locale must be one of: {', '.join(_LOCALE_VALUES)}")


def _create_draft(request, payload: DraftIn, submission_type: str) -> DraftSubmission:
    user = request.auth
    _require_min_participant(user)
    _validate_locale(payload.locale)

    draft = DraftSubmission.objects.create(
        author=user,
        submission_type=submission_type,
        title=payload.title,
        body=payload.body,
        locale=payload.locale,
        category=payload.category,
    )

    if is_admin(user):
        try:
            draft.approve(reviewer=user)
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc

    return draft


def _update_draft(request, pk: int, payload: DraftPatchIn, submission_type: str) -> DraftSubmission:
    user = request.auth
    draft = _get_draft_or_404(pk, submission_type)
    _require_owner_or_admin(user, draft)

    if draft.status != DraftSubmission.Status.PENDING:
        raise HttpError(409, "Only PENDING drafts can be edited")

    data = payload.dict(exclude_unset=True)
    if "locale" in data:
        _validate_locale(data["locale"])

    update_fields = []
    for field, value in data.items():
        setattr(draft, field, value)
        update_fields.append(field)

    if update_fields:
        draft.save(update_fields=update_fields)

    return draft


def _delete_draft(request, pk: int, submission_type: str) -> None:
    user = request.auth
    draft = _get_draft_or_404(pk, submission_type)
    _require_owner_or_admin(user, draft)

    if draft.status != DraftSubmission.Status.PENDING:
        raise HttpError(409, "Only PENDING drafts can be deleted")

    draft.delete()


# -- News endpoints -----------------------------------------------------------


@news_router.get("/", response=list[NewsArticleOut], auth=optional_auth, summary="List news articles")
def list_news(request):
    user = request.auth
    qs = NewsArticle.objects.filter(is_deleted=False)
    if not is_admin(user):
        qs = qs.filter(is_hidden=False)
    return list(qs)


@news_router.get("/{pk}", response=NewsArticleOut, auth=optional_auth, summary="Get news article")
def get_news(request, pk: int):
    user = request.auth
    try:
        article = NewsArticle.objects.get(pk=pk, is_deleted=False)
    except NewsArticle.DoesNotExist:
        raise HttpError(404, "Not found") from None
    if article.is_hidden and not is_admin(user):
        raise HttpError(404, "Not found")
    return article


@news_router.post("/", response={201: DraftOut}, auth=auth, summary="Create news draft")
def create_news_draft(request, payload: DraftIn):
    draft = _create_draft(request, payload, DraftSubmission.SubmissionType.NEWS)
    return 201, draft


@news_router.patch("/{pk}", response=DraftOut, auth=auth, summary="Update news draft")
def update_news_draft(request, pk: int, payload: DraftPatchIn):
    return _update_draft(request, pk, payload, DraftSubmission.SubmissionType.NEWS)


@news_router.delete("/{pk}", response={204: None}, auth=auth, summary="Delete news draft")
def delete_news_draft(request, pk: int):
    _delete_draft(request, pk, DraftSubmission.SubmissionType.NEWS)
    return 204, None


# -- Knowledge article endpoints ----------------------------------------------


@knowledge_router.get("/", response=list[DraftOut], auth=optional_auth, summary="List knowledge article drafts")
def list_knowledge_drafts(request, status: DraftSubmission.Status = DraftSubmission.Status.APPROVED):
    user = request.auth
    if not getattr(user, "is_authenticated", False) and status != DraftSubmission.Status.APPROVED:
        raise HttpError(401, "Unauthorized")
    qs = DraftSubmission.objects.filter(submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    if not is_admin(user) and getattr(user, "is_authenticated", False) and status != DraftSubmission.Status.APPROVED:
        qs = qs.filter(author=user)
    qs = qs.filter(status=status)
    return list(qs)


@knowledge_router.get("/{draft_id}", response=DraftOut, auth=optional_auth, summary="Get knowledge article draft")
def get_knowledge_draft(request, draft_id: int):
    user = request.auth
    draft = _get_draft_or_404(draft_id, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    if draft.status != DraftSubmission.Status.APPROVED:
        if not getattr(user, "is_authenticated", False):
            raise HttpError(404, "Draft not found")
        _require_owner_or_admin(user, draft)
    return draft


@knowledge_router.post("/", response={201: DraftOut}, auth=auth, summary="Create knowledge article draft")
def create_knowledge_draft(request, payload: DraftIn):
    draft = _create_draft(request, payload, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    return 201, draft


@knowledge_router.patch("/{draft_id}", response=DraftOut, auth=auth, summary="Update knowledge article draft")
def update_knowledge_draft(request, draft_id: int, payload: DraftPatchIn):
    return _update_draft(request, draft_id, payload, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)


@knowledge_router.delete("/{draft_id}", response={204: None}, auth=auth, summary="Delete knowledge article draft")
def delete_knowledge_draft(request, draft_id: int):
    _delete_draft(request, draft_id, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    return 204, None
