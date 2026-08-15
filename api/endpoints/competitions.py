from datetime import date

from django.db import transaction
from django.db.models import Q
from ninja import Query, Router, Schema, Status
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from api.schemas import LocalizedStr, LocalizedTitle, Url, localize_field
from calendar_app.models import MAX_DESCRIPTION_LENGTH, Competition, Discipline, EventType
from locations.models import (
    Location,
    LocationConflictError,
    chain_is_approved,
    competition_location_block_reason,
    lock_competition_location,
)

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()
router = Router(tags=["competitions"])


# -- Schemas ---------------------------------------------------------------


class CompetitionIn(Schema):
    title: LocalizedTitle
    description: LocalizedStr = LocalizedStr()
    event_type_ids: list[int] = []  # noqa: RUF012
    discipline_ids: list[int] = []  # noqa: RUF012
    location_id: int | None = None
    date_start: date
    date_end: date | None = None
    url_route: Url = ""
    url_announcement: Url = ""
    url_registration: Url = ""
    url_regulations: Url = ""
    url_results: Url = ""


class CompetitionPatchIn(Schema):
    title: LocalizedTitle | None = None
    description: LocalizedStr | None = None
    event_type_ids: list[int] | None = None
    discipline_ids: list[int] | None = None
    location_id: int | None = None
    date_start: date | None = None
    date_end: date | None = None
    url_route: Url | None = None
    url_announcement: Url | None = None
    url_registration: Url | None = None
    url_regulations: Url | None = None
    url_results: Url | None = None
    is_hidden: bool | None = None


class CompetitionOut(Schema):
    id: int
    title: LocalizedStr
    description: LocalizedStr
    event_type_ids: list[int]
    discipline_ids: list[int]
    location_id: int | None
    # The city the location sits in (its depth-3 ancestor, or itself when it is one). A start venue
    # is too fine a place to compare two events by -- one calendar's "Grebnevo Estate" and another's
    # "other location" are the same race -- while the city is the level both agree on, which is what
    # the import agent's duplicate detection needs.
    location_city_id: int | None
    date_start: date
    date_end: date | None
    status: str
    # Why a submission was rejected. Only non-empty for rejected competitions, which the list and
    # detail endpoints already restrict to the submitter and admins -- so this never leaks another
    # user's rejection reason. Lets an API client (e.g. an agent proposing events) learn from it.
    rejection_reason: str = ""
    submitted_by_id: int | None
    url_route: str
    url_announcement: str
    url_registration: str
    url_regulations: str
    url_results: str
    is_hidden: bool
    is_deleted: bool

    @staticmethod
    def resolve_location_city_id(obj: Competition) -> int | None:
        # The list endpoint resolves every row's city in one query and caches it here; anything else
        # falls back to looking this row's up, so the field is right however the schema is used.
        if hasattr(obj, "_city_id"):
            return obj._city_id
        return city_id_of(obj.location)

    @staticmethod
    def resolve_title(obj: Competition) -> LocalizedStr:
        return localize_field(obj, "title")

    @staticmethod
    def resolve_description(obj: Competition) -> LocalizedStr:
        return localize_field(obj, "description")

    @staticmethod
    def resolve_discipline_ids(obj: Competition) -> list[int]:
        return [d.pk for d in obj.disciplines.all()]

    @staticmethod
    def resolve_event_type_ids(obj: Competition) -> list[int]:
        return [e.pk for e in obj.event_types.all()]


class CompetitionDetailOut(CompetitionOut):
    competition_token: str | None = None

    @staticmethod
    def resolve_competition_token(obj: Competition) -> str | None:
        return getattr(obj, "_api_token", None)


# -- Helpers ---------------------------------------------------------------


_CITY_DEPTH = 3  # country -> region -> city -> venue


def _city_path(location) -> str | None:
    """The treebeard path of the city ``location`` belongs to, or None above city level."""
    if location is None or location.depth < _CITY_DEPTH:
        return None
    step = len(location.path) // location.depth
    return location.path[: step * _CITY_DEPTH]


def city_id_of(location) -> int | None:
    """The id of the city a location sits in (itself when it is one); None above city level."""
    path = _city_path(location)
    if path is None:
        return None
    if location.depth == _CITY_DEPTH:
        return location.pk
    return Location.objects.filter(path=path, depth=_CITY_DEPTH).values_list("pk", flat=True).first()


def _annotate_city_ids(competitions: list) -> list:
    """Resolve every row's city in one query, so serializing a list is not one query per row."""
    wanted = {path for comp in competitions if (path := _city_path(comp.location)) is not None}
    by_path = dict(Location.objects.filter(path__in=wanted, depth=_CITY_DEPTH).values_list("path", "pk"))
    for comp in competitions:
        comp._city_id = by_path.get(_city_path(comp.location))
    return competitions


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
        return (
            Competition.objects.select_related("location")
            .prefetch_related("disciplines", "event_types")
            .get(pk=pk, is_deleted=False)
        )
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


def _lock_location_for_competition(location_id, user):
    """Lock + re-validate the location under its row lock (inside the caller's transaction) so a
    concurrent delete/level-change can't bind a competition to a removed/non-venue node. Returns the
    locked pk (or None). Raises LocationConflictError if it is no longer usable."""
    if location_id is None:
        return None
    locked = lock_competition_location(Location(pk=location_id), user, is_admin=is_admin(user))
    return locked.pk


def _set_disciplines(competition: Competition, discipline_ids: list[int] | None) -> None:
    """Replace the competition's disciplines from a list of IDs, rejecting any that don't exist."""
    if discipline_ids is None:
        return
    ids = list(dict.fromkeys(discipline_ids))  # de-dup, keep order
    disciplines = list(Discipline.objects.filter(pk__in=ids))
    if len(disciplines) != len(ids):
        raise HttpError(404, "Discipline not found")
    competition.disciplines.set(disciplines)


def _set_event_types(competition: Competition, event_type_ids: list[int] | None) -> None:
    """Replace the competition's types from a list of IDs, rejecting any that do not exist."""
    if event_type_ids is None:
        return
    ids = list(dict.fromkeys(event_type_ids))  # de-dup, keep order
    event_types = list(EventType.objects.filter(pk__in=ids))
    if len(event_types) != len(ids):
        raise HttpError(404, "Event type not found")
    competition.event_types.set(event_types)


def _demote_for_pending_geography(competition: Competition, user) -> bool:
    """Send a published competition back for review when its location is still a proposal.

    Returns whether it changed anything. An admin (who may approve the geography) is exempt; the
    venue itself is fine -- only pending *ancestors* matter, since an organizer may add a venue.
    """
    location = competition.location
    if (
        competition.status == Competition.Status.APPROVED
        and not is_admin(user)
        and location is not None
        and not chain_is_approved(location.get_parent())
    ):
        competition.status = Competition.Status.PENDING_APPROVAL
        competition.approved_by = None
        competition.approved_at = None
        return True
    return False


def _apply_patch_fields(competition: Competition, data: dict, user) -> list[str]:
    """Apply scalar/localized/location fields from a PATCH payload; return the changed columns.

    The disciplines M2M is handled separately by the caller (it isn't an update_fields column).
    """
    update_fields: list[str] = []
    for field, value in data.items():
        if isinstance(value, dict) and field in ("title", "description"):
            loc = LocalizedStr(**value)
            if field == "description":
                _validate_description_length(loc)
            # Descriptions are sanitized centrally in Competition.save().
            update_fields.extend(_apply_localized(competition, field, loc))
        elif field == "location_id":
            competition.location_id = _lock_location_for_competition(value, user)
            update_fields.append("location_id")
            # Re-pointing a published event at geography still under review publishes that branch,
            # and then it can never be rejected. Mirror the web edit: send such an event back for
            # review unless the caller may bless geography anyway.
            if _demote_for_pending_geography(competition, user):
                update_fields += ["status", "approved_by", "approved_at"]
        else:
            setattr(competition, field, value)
            update_fields.append(field)
    return update_fields


def _to_detail(competition: Competition, user=None) -> Competition:
    """Attach competition_token to obj for serialization (avoids extra dict merging)."""
    can_see = user is not None and (_is_owner(user, competition) or is_admin(user))
    # upload_token is nullable (a manager can delete it); don't serialize a null as "None".
    competition._api_token = str(competition.upload_token) if can_see and competition.upload_token else None
    return competition


def _listable_by(qs, user, deleted: bool):
    """Narrow a competition list to what ``user`` is allowed to see.

    A deleted competition is off the site, so it is never public: only its author -- in practice
    the import agent asking what it submitted -- and admins may list it. The agent needs that to
    tell an event it proposed was thrown away and stop proposing it; without it, deleting an
    unwanted event only hides it until the next nightly run puts it back.
    """
    if deleted:
        if not getattr(user, "is_authenticated", False):
            raise HttpError(401, "Authentication is required to list deleted competitions.")
        return qs if is_admin(user) else qs.filter(submitted_by=user)
    if is_admin(user):
        return qs
    visible = Q(status=Competition.Status.APPROVED, is_hidden=False)
    if getattr(user, "is_authenticated", False):
        visible |= Q(submitted_by=user)
    return qs.filter(visible)


# -- Endpoints -------------------------------------------------------------


@router.get("/", response=list[CompetitionOut], auth=optional_auth, summary="List competitions")
def list_competitions(
    request,
    status: Competition.Status = Competition.Status.APPROVED,
    discipline_ids: list[int] = Query(default=[]),  # noqa: B008
    direction_ids: list[int] = Query(default=[]),  # noqa: B008
    event_type_ids: list[int] = Query(default=[]),  # noqa: B008
    location_ids: list[int] = Query(default=[]),  # noqa: B008
    only_favorite: bool = False,
    deleted: bool = False,
):
    user = request.auth
    # Both id lists in the response walk a many-to-many, so prefetch each: one query per set for
    # the whole page instead of one per row.
    qs = _listable_by(
        Competition.objects.filter(is_deleted=deleted).prefetch_related("disciplines", "event_types"),
        user,
        deleted,
    )
    qs = qs.filter(status=status)
    # discipline_ids and direction_ids (DisciplineCategory) are the same taxonomy dimension and are
    # OR-ed, matching the web calendar/list/map: a competition matches if it has a selected discipline
    # OR a discipline in a selected direction. distinct() drops the duplicate M2M-join rows.
    if discipline_ids or direction_ids:
        match = Q()
        if discipline_ids:
            match |= Q(disciplines__id__in=discipline_ids)
        if direction_ids:
            match |= Q(disciplines__category_id__in=direction_ids)
        qs = qs.filter(match).distinct()
    if event_type_ids:
        # A competition may carry several types, so the join can repeat a row.
        qs = qs.filter(event_types__id__in=event_type_ids).distinct()
    if location_ids:
        qs = qs.filter(location_id__in=_descendant_location_ids(list(location_ids)))
    # only_favorite restricts to the authenticated user's favorites (issue #183). There is no way
    # to favorite via the API -- it is filter-only -- so an anonymous caller has no favorites and
    # asking for them is a 401 rather than a silently empty list.
    if only_favorite:
        if not getattr(user, "is_authenticated", False):
            raise HttpError(401, "Authentication is required to filter by favorites.")
        qs = qs.filter(favorited_by__user=user)
    return _annotate_city_ids(list(qs.select_related("location")))


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
        "date_start",
        "date_end",
        "url_route",
        "url_announcement",
        "url_registration",
        "url_regulations",
        "url_results",
    ):
        setattr(competition, field, getattr(payload, field))

    try:
        # Lock + re-validate the location and save in one transaction so a concurrent
        # delete/level-change can't bind the competition to a removed or non-venue node.
        with transaction.atomic():
            competition.location_id = _lock_location_for_competition(payload.location_id, user)
            # An admin's competition is created approved -- but not onto geography still under
            # review: that would publish the branch and, if it is another user's proposal, hold it
            # hostage (its rejection is blocked while approved work sits inside). Publish only where
            # the geography above the venue is already public; otherwise leave it pending.
            if competition.status == Competition.Status.APPROVED and not chain_is_approved(
                competition.location.get_parent() if competition.location else None
            ):
                competition.status = Competition.Status.PENDING_APPROVAL
            competition.save()
            _set_disciplines(competition, payload.discipline_ids)
            _set_event_types(competition, payload.event_type_ids)
            if competition.status == Competition.Status.APPROVED and competition.location is not None:
                competition.location.approve_with_competition(user)
    except LocationConflictError:
        raise HttpError(409, "Location is no longer usable for a competition") from None
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
    # Unambiguous discipline semantics: omit = leave unchanged, [] = clear, null = error.
    if "discipline_ids" in data and data["discipline_ids"] is None:
        raise HttpError(422, "discipline_ids cannot be null; pass [] to clear")
    if "event_type_ids" in data and data["event_type_ids"] is None:
        raise HttpError(422, "event_type_ids cannot be null; pass [] to clear")

    # disciplines is a many-to-many: set it after the row is saved, not via update_fields.
    set_disciplines = "discipline_ids" in data
    discipline_ids = data.pop("discipline_ids", None)
    set_event_types = "event_type_ids" in data
    event_type_ids = data.pop("event_type_ids", None)

    try:
        # Lock + re-validate a changed location and save in one transaction so a concurrent
        # delete/level-change can't bind the competition to a removed or non-venue node.
        with transaction.atomic():
            update_fields = _apply_patch_fields(competition, data, user)
            if update_fields:
                competition.save(update_fields=update_fields)
            if set_disciplines:
                _set_disciplines(competition, discipline_ids)
            if set_event_types:
                _set_event_types(competition, event_type_ids)
    except LocationConflictError:
        raise HttpError(409, "Location is no longer usable for a competition") from None

    return _to_detail(competition, user)


@router.post(
    "/{competition_id}/resubmit",
    response=CompetitionOut,
    auth=auth,
    summary="Resubmit a rejected competition for review (owner)",
)
def resubmit_competition(request, competition_id: int):
    user = request.auth
    competition = _get_or_404(competition_id)
    _require_visible_or_404(user, competition)
    _require_owner_or_admin(user, competition)
    if competition.status != Competition.Status.REJECTED:
        raise HttpError(409, "Only a rejected competition can be resubmitted for review")
    competition.resubmit()
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
