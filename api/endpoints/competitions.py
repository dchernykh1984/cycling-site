from datetime import date

from ninja import Query, Router, Schema
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, is_admin
from api.schemas import LocalizedStr
from calendar_app.models import Competition
from locations.models import Location

auth = ApiTokenAuth()
router = Router(tags=["competitions"])


# -- Schemas ---------------------------------------------------------------


class CompetitionIn(Schema):
    title: LocalizedStr
    description: LocalizedStr = LocalizedStr()
    event_type_id: int | None = None
    discipline_id: int | None = None
    location_id: int | None = None
    date_start: date
    date_end: date | None = None
    url_route: str = ""
    url_announcement: str = ""
    url_registration: str = ""
    url_regulations: str = ""
    url_results: str = ""


class CompetitionPatchIn(Schema):
    title: LocalizedStr | None = None
    description: LocalizedStr | None = None
    event_type_id: int | None = None
    discipline_id: int | None = None
    location_id: int | None = None
    date_start: date | None = None
    date_end: date | None = None
    url_route: str | None = None
    url_announcement: str | None = None
    url_registration: str | None = None
    url_regulations: str | None = None
    url_results: str | None = None
    is_hidden: bool | None = None


class CompetitionOut(Schema):
    id: int
    title: LocalizedStr
    description: LocalizedStr
    event_type_id: int | None
    discipline_id: int | None
    location_id: int | None
    date_start: date
    date_end: date | None
    status: str
    submitted_by_id: int | None
    url_route: str
    url_announcement: str
    url_registration: str
    url_regulations: str
    url_results: str
    is_hidden: bool
    is_deleted: bool

    @staticmethod
    def resolve_title(obj: Competition) -> LocalizedStr:
        return LocalizedStr(ru=obj.title_ru or "", kk=obj.title_kk or "", en=obj.title_en or "")

    @staticmethod
    def resolve_description(obj: Competition) -> LocalizedStr:
        return LocalizedStr(ru=obj.description_ru or "", kk=obj.description_kk or "", en=obj.description_en or "")


class CompetitionDetailOut(CompetitionOut):
    competition_token: str | None = None

    @staticmethod
    def resolve_competition_token(obj: Competition) -> str | None:
        return getattr(obj, "_api_token", None)


# -- Helpers ---------------------------------------------------------------


def _descendant_location_ids(location_ids: list[int]) -> set[int]:
    """Return PKs of all locations at or below the given location IDs (treebeard path prefix match)."""
    if not location_ids:
        return set()
    from django.db.models import Q

    roots = Location.objects.filter(pk__in=location_ids).values_list("path", flat=True)
    if not roots:
        return set()
    q = Q()
    for path in roots:
        q |= Q(path__startswith=path)
    return set(Location.objects.filter(q).values_list("pk", flat=True))


def _is_owner(user, competition: Competition) -> bool:
    return competition.submitted_by_id == user.pk


def _get_or_404(pk: int) -> Competition:
    try:
        return Competition.objects.select_related("event_type", "discipline", "location").get(pk=pk, is_deleted=False)
    except Competition.DoesNotExist:
        raise HttpError(404, "Competition not found") from None


def _require_owner_or_admin(user, competition: Competition) -> None:
    if not (_is_owner(user, competition) or is_admin(user)):
        raise HttpError(403, "Forbidden")


def _apply_localized(obj, field: str, value: LocalizedStr) -> list[str]:
    """Set all three language variants of a translated field; return the updated field names."""
    updated = []
    for lang, val in (("ru", value.ru), ("kk", value.kk), ("en", value.en)):
        setattr(obj, f"{field}_{lang}", val)
        updated.append(f"{field}_{lang}")
    return updated


def _to_detail(competition: Competition, user=None) -> Competition:
    """Attach competition_token to obj for serialization (avoids extra dict merging)."""
    competition._api_token = (
        str(competition.upload_token) if user is not None and (_is_owner(user, competition) or is_admin(user)) else None
    )
    return competition


# -- Endpoints -------------------------------------------------------------


@router.get("/", response=list[CompetitionOut], auth=auth, summary="List competitions")
def list_competitions(
    request,
    status: str | None = None,
    discipline_ids: list[int] = Query(default=[]),  # noqa: B008
    event_type_ids: list[int] = Query(default=[]),  # noqa: B008
    country_ids: list[int] = Query(default=[]),  # noqa: B008
    region_ids: list[int] = Query(default=[]),  # noqa: B008
    city_ids: list[int] = Query(default=[]),  # noqa: B008
):
    qs = Competition.objects.filter(is_deleted=False)
    qs = qs.filter(status=status) if status else qs.filter(status=Competition.Status.APPROVED)
    if discipline_ids:
        qs = qs.filter(discipline_id__in=discipline_ids)
    if event_type_ids:
        qs = qs.filter(event_type_id__in=event_type_ids)
    for loc_ids in (country_ids, region_ids, city_ids):
        if loc_ids:
            qs = qs.filter(location_id__in=_descendant_location_ids(loc_ids))
    return list(qs)


@router.get("/{competition_id}", response=CompetitionDetailOut, auth=auth, summary="Get competition detail")
def get_competition(request, competition_id: int):
    competition = _get_or_404(competition_id)
    return _to_detail(competition, request.auth)


@router.post("/", response={201: CompetitionDetailOut}, auth=auth, summary="Create competition")
def create_competition(request, payload: CompetitionIn):
    user = request.auth
    if user.get_role_rank() < user.ROLE_HIERARCHY.index(user.Role.ORGANIZER):
        raise HttpError(403, "ORGANIZER role or higher is required")

    status = Competition.Status.APPROVED if is_admin(user) else Competition.Status.PENDING_APPROVAL
    competition = Competition(submitted_by=user, status=status)
    _apply_localized(competition, "title", payload.title)
    _apply_localized(competition, "description", payload.description)

    for field in (
        "event_type_id",
        "discipline_id",
        "location_id",
        "date_start",
        "date_end",
        "url_route",
        "url_announcement",
        "url_registration",
        "url_regulations",
        "url_results",
    ):
        setattr(competition, field, getattr(payload, field))

    competition.save()
    return 201, _to_detail(competition, user)


@router.patch("/{competition_id}", response=CompetitionDetailOut, auth=auth, summary="Update competition")
def update_competition(request, competition_id: int, payload: CompetitionPatchIn):
    user = request.auth
    competition = _get_or_404(competition_id)
    _require_owner_or_admin(user, competition)

    data = payload.dict(exclude_unset=True)

    if "is_hidden" in data and not is_admin(user):
        raise HttpError(403, "Only admins can change visibility")

    update_fields: list[str] = []

    for field, value in data.items():
        if isinstance(value, dict) and field in ("title", "description"):
            loc = LocalizedStr(**value)
            update_fields.extend(_apply_localized(competition, field, loc))
        else:
            setattr(competition, field, value)
            update_fields.append(field)

    if update_fields:
        competition.save(update_fields=update_fields)

    return _to_detail(competition, user)


@router.delete("/{competition_id}", response={204: None}, auth=auth, summary="Delete competition (soft)")
def delete_competition(request, competition_id: int):
    user = request.auth
    competition = _get_or_404(competition_id)
    _require_owner_or_admin(user, competition)
    competition.is_deleted = True
    competition.save(update_fields=["is_deleted"])
    return 204, None
