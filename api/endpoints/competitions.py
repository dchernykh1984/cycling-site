from datetime import date

from django.db.models import Q
from ninja import Query, Router, Schema, Status
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from api.schemas import LocalizedStr, localize_field
from calendar_app.models import MAX_DESCRIPTION_LENGTH, Competition
from locations.models import Location, competition_location_block_reason

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()
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
        return localize_field(obj, "title")

    @staticmethod
    def resolve_description(obj: Competition) -> LocalizedStr:
        return localize_field(obj, "description")


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
    paths = list(Location.objects.filter(pk__in=location_ids).values_list("path", flat=True))
    if not paths:
        return set()
    q = Q()
    for path in paths:
        q |= Q(path__startswith=path)
    return set(Location.objects.filter(q).values_list("pk", flat=True))


def _is_owner(user, competition: Competition) -> bool:
    uid = getattr(user, "pk", None)
    return uid is not None and competition.submitted_by_id == uid


def _get_or_404(pk: int) -> Competition:
    try:
        return Competition.objects.select_related("event_type", "discipline", "location").get(pk=pk, is_deleted=False)
    except Competition.DoesNotExist:
        raise HttpError(404, "Competition not found") from None


def _require_owner_or_admin(user, competition: Competition) -> None:
    if not (_is_owner(user, competition) or is_admin(user)):
        raise HttpError(403, "Forbidden")


def _require_visible_or_404(user, competition: Competition) -> None:
    is_privileged = _is_owner(user, competition) or is_admin(user)
    if not is_privileged and (competition.status != Competition.Status.APPROVED or competition.is_hidden):
        raise HttpError(404, "Competition not found")


def _apply_localized(obj, field: str, value: LocalizedStr) -> list[str]:
    """Set all three language variants of a translated field; return the updated field names."""
    updated = []
    for lang, val in (("ru", value.ru), ("kk", value.kk), ("en", value.en)):
        setattr(obj, f"{field}_{lang}", val)
        updated.append(f"{field}_{lang}")
    # Keep the canonical column in sync via __dict__: setattr(obj, field, ...) would go through
    # modeltranslation's descriptor and, under a non-default active language, write the value
    # into that language's column instead (corrupting an otherwise-empty translation).
    obj.__dict__[field] = value.ru or value.kk or value.en
    updated.append(field)
    return updated


def _validate_description_length(value: LocalizedStr) -> None:
    """Reject an oversized description (inline images are base64) on the untrusted API path."""
    for loc in (value.ru, value.kk, value.en):
        if loc and len(loc) > MAX_DESCRIPTION_LENGTH:
            raise HttpError(422, f"Description is too large (max {MAX_DESCRIPTION_LENGTH} characters)")


def _validate_location_id(location_id, user) -> None:
    """Reject a forged location_id: missing, deleted, or another user's pending proposal (review #3)."""
    if location_id is None:
        return
    location = Location.objects.filter(pk=location_id).first()
    if location is None:
        raise HttpError(404, "Location not found")
    reason = competition_location_block_reason(location, user, is_admin=is_admin(user))
    if reason:
        raise HttpError(403, reason)


def _to_detail(competition: Competition, user=None) -> Competition:
    """Attach competition_token to obj for serialization (avoids extra dict merging)."""
    competition._api_token = (
        str(competition.upload_token) if user is not None and (_is_owner(user, competition) or is_admin(user)) else None
    )
    return competition


# -- Endpoints -------------------------------------------------------------


@router.get("/", response=list[CompetitionOut], auth=optional_auth, summary="List competitions")
def list_competitions(
    request,
    status: Competition.Status = Competition.Status.APPROVED,
    discipline_ids: list[int] = Query(default=[]),  # noqa: B008
    event_type_ids: list[int] = Query(default=[]),  # noqa: B008
    location_ids: list[int] = Query(default=[]),  # noqa: B008
):
    user = request.auth
    qs = Competition.objects.filter(is_deleted=False)
    if not is_admin(user):
        base_q = Q(status=Competition.Status.APPROVED, is_hidden=False)
        if getattr(user, "is_authenticated", False):
            base_q |= Q(submitted_by=user)
        qs = qs.filter(base_q)
    qs = qs.filter(status=status)
    if discipline_ids:
        qs = qs.filter(discipline_id__in=discipline_ids)
    if event_type_ids:
        qs = qs.filter(event_type_id__in=event_type_ids)
    if location_ids:
        qs = qs.filter(location_id__in=_descendant_location_ids(list(location_ids)))
    return list(qs)


@router.get("/{competition_id}", response=CompetitionDetailOut, auth=optional_auth, summary="Get competition detail")
def get_competition(request, competition_id: int):
    competition = _get_or_404(competition_id)
    user = request.auth
    _require_visible_or_404(user, competition)
    return _to_detail(competition, user)


@router.post("/", response={201: CompetitionDetailOut}, auth=auth, summary="Create competition")
def create_competition(request, payload: CompetitionIn):
    user = request.auth
    if user.get_role_rank() < user.ROLE_HIERARCHY.index(user.Role.ORGANIZER):
        raise HttpError(403, "ORGANIZER role or higher is required")

    _validate_location_id(payload.location_id, user)
    status = Competition.Status.APPROVED if is_admin(user) else Competition.Status.PENDING_APPROVAL
    competition = Competition(submitted_by=user, status=status)
    _validate_description_length(payload.description)
    _apply_localized(competition, "title", payload.title)
    # Descriptions are sanitized centrally in Competition.save().
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
    return Status(201, _to_detail(competition, user))


@router.patch("/{competition_id}", response=CompetitionDetailOut, auth=auth, summary="Update competition")
def update_competition(request, competition_id: int, payload: CompetitionPatchIn):
    user = request.auth
    competition = _get_or_404(competition_id)
    _require_visible_or_404(user, competition)
    _require_owner_or_admin(user, competition)

    data = payload.dict(exclude_unset=True)

    if "is_hidden" in data and not is_admin(user):
        raise HttpError(403, "Only admins can change visibility")
    if "location_id" in data:
        _validate_location_id(data["location_id"], user)

    update_fields: list[str] = []

    for field, value in data.items():
        if isinstance(value, dict) and field in ("title", "description"):
            loc = LocalizedStr(**value)
            if field == "description":
                _validate_description_length(loc)
            # Descriptions are sanitized centrally in Competition.save().
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
    _require_visible_or_404(user, competition)
    _require_owner_or_admin(user, competition)
    competition.is_deleted = True
    competition.save(update_fields=["is_deleted"])
    return Status(204, None)
