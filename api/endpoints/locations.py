from decimal import Decimal

from ninja import Router, Schema
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, is_admin
from api.schemas import LocalizedStr
from locations.models import Location

auth = ApiTokenAuth()
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
        return LocalizedStr(ru=obj.name_ru or "", kk=obj.name_kk or "", en=obj.name_en or "")

    @staticmethod
    def resolve_parent_id(obj: Location) -> int | None:
        # list_locations pre-computes _parent_pk via path arithmetic to avoid N+1
        if hasattr(obj, "_parent_pk"):
            return obj._parent_pk
        parent = obj.get_parent()
        return parent.pk if parent else None


# -- Helpers ---------------------------------------------------------------


def _require_admin(user) -> None:
    if not is_admin(user):
        raise HttpError(403, "ADMIN role or higher is required")


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


@router.get("/", response=list[LocationOut], auth=None, summary="List locations")
def list_locations(request, include_hidden: bool = False):
    # Load all non-deleted locations in one query for path-based parent resolution.
    all_locs = list(Location.objects.filter(is_deleted=False))
    step = Location.steplen
    path_to_pk = {loc.path: loc.pk for loc in all_locs}
    for loc in all_locs:
        parent_path = loc.path[:-step] if len(loc.path) > step else None
        loc._parent_pk = path_to_pk.get(parent_path) if parent_path else None
    if not include_hidden:
        return [loc for loc in all_locs if not loc.is_hidden]
    return all_locs


@router.get("/{location_id}", response=LocationOut, auth=None, summary="Get location detail")
def get_location(request, location_id: int):
    return _get_or_404(location_id)


@router.post("/", response={201: LocationOut}, auth=auth, summary="Create location (ADMIN+)")
def create_location(request, payload: LocationIn):
    user = request.auth
    _require_admin(user)

    kwargs = dict(
        name=payload.name.ru or payload.name.kk or payload.name.en,
        name_ru=payload.name.ru,
        name_kk=payload.name.kk,
        name_en=payload.name.en,
        lat=payload.lat,
        lng=payload.lng,
        is_hidden=payload.is_hidden,
    )

    if payload.parent_id is not None:
        try:
            parent = Location.objects.get(pk=payload.parent_id, is_deleted=False)
        except Location.DoesNotExist:
            raise HttpError(404, "Parent location not found") from None
        location = parent.add_child(**kwargs)
    else:
        location = Location.add_root(**kwargs)

    return 201, location


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
    location.is_deleted = True
    location.save(update_fields=["is_deleted"])
    return 204, None
