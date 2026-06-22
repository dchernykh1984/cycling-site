from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from ninja import Router, Schema, Status
from ninja.errors import HttpError
from ninja.schema import Field

from accounts.models import User
from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from api.schemas import LocalizedStr, localize_field
from locations.models import (
    Location,
    LocationConflictError,
    LocationProposal,
    add_location_child,
    soft_delete_location,
)

_PARTICIPANT_RANK = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()
router = Router(tags=["locations"])


# -- Schemas ---------------------------------------------------------------


class LocationIn(Schema):
    name: LocalizedStr
    parent_id: int | None = None
    lat: Decimal | None = None
    lng: Decimal | None = None
    is_hidden: bool = False


class LocationPatchIn(Schema):
    name: LocalizedStr | None = None
    lat: Decimal | None = None
    lng: Decimal | None = None
    is_hidden: bool | None = None


class LocationOut(Schema):
    id: int
    name: LocalizedStr
    parent_id: int | None
    depth: int
    lat: Decimal | None
    lng: Decimal | None
    is_hidden: bool
    is_deleted: bool

    @staticmethod
    def resolve_name(obj: Location) -> LocalizedStr:
        return localize_field(obj, "name")

    @staticmethod
    def resolve_parent_id(obj: Location) -> int | None:
        # list_locations pre-computes _parent_pk via path arithmetic to avoid N+1
        if hasattr(obj, "_parent_pk"):
            return obj._parent_pk
        parent = obj.get_parent()
        return parent.pk if parent else None


class LocationNodeOut(Schema):
    id: int
    name: LocalizedStr
    lat: Decimal | None
    lng: Decimal | None
    is_hidden: bool
    children: list["LocationNodeOut"] = Field(default_factory=list)


LocationNodeOut.model_rebuild()


# -- Helpers ---------------------------------------------------------------


def _require_admin(user) -> None:
    if not is_admin(user):
        raise HttpError(403, "ADMIN role or higher is required")


def _role_rank(user) -> int:
    return user.get_role_rank() if hasattr(user, "get_role_rank") else -1


def _can_add_directly(user) -> bool:
    """Organizer+ create approved locations directly (issue #111)."""
    return bool(getattr(user, "is_superuser", False)) or _role_rank(user) >= _ORGANIZER_RANK


def _proposal_visible(location: Location, user) -> bool:
    """A pending proposed location is visible only to its proposer (or an admin)."""
    proposal = getattr(location, "proposal", None)
    if proposal is None or proposal.status == LocationProposal.Status.APPROVED:
        return True
    if is_admin(user):
        return True
    return getattr(user, "is_authenticated", False) and proposal.submitted_by_id == user.pk


def _visible_locations_qs(user):
    """Non-deleted locations honouring proposal visibility (pending = proposer/admin only)."""
    qs = Location.objects.filter(is_deleted=False)
    if is_admin(user):
        return qs
    visible = Q(proposal__isnull=True) | Q(proposal__status=LocationProposal.Status.APPROVED)
    if getattr(user, "is_authenticated", False):
        visible |= Q(proposal__status=LocationProposal.Status.PENDING_APPROVAL, proposal__submitted_by=user)
    return qs.filter(visible)


def _get_or_404(pk: int) -> Location:
    try:
        return Location.objects.get(pk=pk, is_deleted=False)
    except Location.DoesNotExist:
        raise HttpError(404, "Location not found") from None


def _apply_name(location: Location, name: LocalizedStr) -> None:
    location.name_ru = name.ru
    location.name_kk = name.kk
    location.name_en = name.en
    # modeltranslation uses the first non-empty language as the canonical name
    location.name = name.ru or name.kk or name.en


# -- Endpoints -------------------------------------------------------------


@router.get("/", response=list[LocationNodeOut], auth=optional_auth, summary="List locations as hierarchy tree")
def list_locations(request, include_hidden: bool = False):
    if include_hidden and not is_admin(request.auth):
        include_hidden = False
    all_locs = list(_visible_locations_qs(request.auth))
    step = Location.steplen
    path_to_loc: dict[str, Location] = {loc.path: loc for loc in all_locs}
    children_map: dict[int, list[Location]] = {loc.pk: [] for loc in all_locs}
    roots: list[Location] = []
    for loc in all_locs:
        parent_path = loc.path[:-step] if len(loc.path) > step else None
        parent = path_to_loc.get(parent_path) if parent_path else None
        if parent is not None:
            children_map[parent.pk].append(loc)
        else:
            roots.append(loc)

    def build_node(loc: Location) -> LocationNodeOut:
        kids = children_map[loc.pk]
        if not include_hidden:
            kids = [c for c in kids if not c.is_hidden]
        return LocationNodeOut(
            id=loc.pk,
            name=localize_field(loc, "name"),
            lat=loc.lat,
            lng=loc.lng,
            is_hidden=loc.is_hidden,
            children=[build_node(c) for c in kids],
        )

    visible_roots = [r for r in roots if include_hidden or not r.is_hidden]
    return [build_node(r) for r in visible_roots]


@router.get("/{location_id}", response=LocationOut, auth=optional_auth, summary="Get location detail")
def get_location(request, location_id: int):
    location = _get_or_404(location_id)
    if location.is_hidden and not is_admin(request.auth):
        raise HttpError(404, "Location not found")
    # A pending proposed location is visible only to its proposer (or an admin).
    if not _proposal_visible(location, request.auth):
        raise HttpError(404, "Location not found")
    return location


@router.post(
    "/",
    response={201: LocationOut},
    auth=auth,
    summary="Create location (organizer+ approved; participant proposes; pending until reviewed)",
)
def create_location(request, payload: LocationIn):
    user = request.auth
    if _role_rank(user) < _PARTICIPANT_RANK and not getattr(user, "is_superuser", False):
        raise HttpError(403, "PARTICIPANT role or higher is required")
    approved = _can_add_directly(user)

    kwargs = dict(
        name=payload.name.ru or payload.name.kk or payload.name.en,
        name_ru=payload.name.ru,
        name_kk=payload.name.kk,
        name_en=payload.name.en,
        lat=payload.lat,
        lng=payload.lng,
        # Only managers may create hidden fallback venues.
        is_hidden=payload.is_hidden if is_admin(user) else False,
    )

    parent = None
    if payload.parent_id is not None:
        try:
            parent = Location.objects.get(pk=payload.parent_id, is_deleted=False)
        except Location.DoesNotExist:
            raise HttpError(404, "Parent location not found") from None

    # Non-admins may only create a venue (depth 4) under a city (depth 3); building the
    # geographic hierarchy (root/region/city) is admin-only (review #2).
    if not is_admin(user) and (parent is None or parent.depth != 3):
        raise HttpError(403, "A city (depth-3) parent_id is required to create a venue")

    # add_location_child locks the parent (or the root namespace) and the proposal shares the
    # transaction, so a concurrent delete can't orphan the node and two roots can't collide on path.
    try:
        with transaction.atomic():
            location = add_location_child(parent, **kwargs)
            # Below organizer the location is a proposal: usable by the author, pending review.
            if not approved:
                LocationProposal.objects.create(location=location, submitted_by=user)
    except LocationConflictError:
        raise HttpError(409, "Parent location is no longer available") from None

    return Status(201, location)


@router.patch("/{location_id}", response=LocationOut, auth=auth, summary="Update location (ADMIN+)")
def update_location(request, location_id: int, payload: LocationPatchIn):
    user = request.auth
    _require_admin(user)
    location = _get_or_404(location_id)

    data = payload.dict(exclude_unset=True)
    update_fields: list[str] = []

    for field, value in data.items():
        if field == "name" and isinstance(value, dict):
            loc = LocalizedStr(**value)
            _apply_name(location, loc)
            update_fields.extend(["name", "name_ru", "name_kk", "name_en"])
        else:
            setattr(location, field, value)
            update_fields.append(field)

    if update_fields:
        location.save(update_fields=update_fields)

    return location


@router.delete("/{location_id}", response={204: None}, auth=auth, summary="Delete location (ADMIN+, soft)")
def delete_location(request, location_id: int):
    user = request.auth
    _require_admin(user)
    location = _get_or_404(location_id)
    # Same contract as the web form: refuse to orphan a live subtree/competitions. soft_delete_location
    # re-checks under a row lock, so a concurrent create can't slip a child in before the delete.
    try:
        soft_delete_location(location)
    except LocationConflictError:
        raise HttpError(409, "Location still has nested locations or competitions") from None
    return Status(204, None)
