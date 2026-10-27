"""Virtual ride: a member's saved rides and records, group races, and riding together.

The trainer page (trainer/static/trainer/alatau.html) calls these from the member's browser with
their session; API clients use the personal Bearer token like everywhere else in /api/v1/.
"""

from datetime import datetime, timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from ninja.security import django_auth

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from trainer import live, records
from trainer.models import GroupRide, GroupRideMember, LiveRider, VirtualRide

router = Router(tags=["virtual-ride"])

# A member signed in on the site (the trainer page) or holding a personal API token.
member_auth = [ApiTokenAuth(), django_auth]

_ROUTE = r"^[a-z0-9][a-z0-9_-]{0,39}$"
_MAX_HISTORY = 100


# -- Schemas ---------------------------------------------------------------


class MeOut(Schema):
    authenticated: bool
    user_id: int | None = None
    name: str = ""
    profile_url: str = ""
    login_url: str = ""


class RideIn(Schema):
    route: str = Field(..., pattern=_ROUTE, max_length=40)
    route_name: str = Field("", max_length=120)
    kind: VirtualRide.Kind = VirtualRide.Kind.RACE
    group_id: int | None = None
    duration_s: float = Field(..., gt=0, le=24 * 3600)
    distance_m: float = Field(..., ge=0, le=1_000_000)
    elevation_gain_m: float = Field(0, ge=0, le=20_000)
    avg_speed_kmh: float = Field(0, ge=0, le=120)
    max_speed_kmh: float = Field(0, ge=0, le=150)
    avg_power_w: int | None = Field(None, ge=0, le=3000)
    avg_cadence_rpm: int | None = Field(None, ge=0, le=250)
    avg_hr_bpm: int | None = Field(None, ge=0, le=260)
    max_hr_bpm: int | None = Field(None, ge=0, le=260)
    power_source: VirtualRide.PowerSource = VirtualRide.PowerSource.ESTIMATED
    place: int | None = Field(None, ge=1, le=10_000)
    field_size: int | None = Field(None, ge=1, le=10_000)
    peak_5s_w: int | None = Field(None, ge=0, le=3000)
    peak_1m_w: int | None = Field(None, ge=0, le=3000)
    peak_5m_w: int | None = Field(None, ge=0, le=3000)
    peak_20m_w: int | None = Field(None, ge=0, le=3000)


class RideOut(Schema):
    id: int
    route: str
    route_name: str
    kind: str
    group_id: int | None
    finished_at: datetime
    duration_s: float
    distance_m: float
    elevation_gain_m: float
    avg_speed_kmh: float
    max_speed_kmh: float
    avg_power_w: int | None
    avg_cadence_rpm: int | None
    avg_hr_bpm: int | None
    max_hr_bpm: int | None
    power_source: str
    place: int | None
    field_size: int | None
    peak_5s_w: int | None
    peak_1m_w: int | None
    peak_5m_w: int | None
    peak_20m_w: int | None


class SavedRideOut(Schema):
    ride: RideOut
    records: list[str]


class RouteBestOut(Schema):
    route: str
    route_name: str
    duration_s: float
    finished_at: datetime
    attempts: int
    best_avg_power_w: int | None


class RecordsOut(Schema):
    rides: int
    distance_km: float
    elevation_m: int
    time_s: int
    max_speed_kmh: float | None
    peaks: dict[str, int | None]
    routes: list[RouteBestOut]


class MemberOut(Schema):
    user_id: int
    name: str


class GroupOut(Schema):
    id: int
    route: str
    route_name: str
    start_at: datetime
    host: MemberOut
    members: list[MemberOut]
    is_member: bool
    is_host: bool


class GroupIn(Schema):
    route: str = Field(..., pattern=_ROUTE, max_length=40)
    route_name: str = Field("", max_length=120)
    start_in_s: int = Field(60, ge=live.MIN_START_DELAY_S, le=live.MAX_START_DELAY_S)


class GroupResultOut(Schema):
    user_id: int
    name: str
    duration_s: float
    finished_at: datetime


class GroupResultsOut(Schema):
    group: GroupOut
    finished: list[GroupResultOut]


class PresenceIn(Schema):
    status: LiveRider.Status = LiveRider.Status.LOBBY
    route: str = Field("", pattern=r"^$|" + _ROUTE, max_length=40)
    mode: VirtualRide.Kind = VirtualRide.Kind.RACE
    group_id: int | None = None
    distance_m: float = Field(0, ge=-1000, le=1_000_000)
    speed_ms: float = Field(0, ge=0, le=40)
    cadence_rpm: int = Field(0, ge=0, le=250)
    power_w: int = Field(0, ge=0, le=3000)
    lane_m: float = Field(2, ge=0, le=15)
    finished_s: float | None = Field(None, ge=0, le=24 * 3600)


class OnlineOut(Schema):
    user_id: int
    name: str
    status: str
    route: str
    mode: str
    group_id: int | None


class RiderOut(OnlineOut):
    distance_m: float
    speed_ms: float
    cadence_rpm: int
    power_w: int
    lane_m: float
    finished_s: float | None
    age_s: float


class PresenceOut(Schema):
    server_now: datetime
    online: list[OnlineOut]
    groups: list[GroupOut]
    riders: list[RiderOut]


# -- Helpers ---------------------------------------------------------------


def _member(user) -> MemberOut:
    return MemberOut(user_id=user.pk, name=user.public_display_name)


def _group_out(group: GroupRide, user) -> GroupOut:
    members = [m.user for m in group.memberships.all()]
    return GroupOut(
        id=group.pk,
        route=group.route,
        route_name=group.route_name,
        start_at=group.start_at,
        host=_member(group.host),
        members=[_member(u) for u in members],
        is_member=any(u.pk == user.pk for u in members),
        is_host=group.host_id == user.pk,
    )


def _open_group(group_id: int) -> GroupRide:
    group = get_object_or_404(GroupRide.objects.select_related("host"), pk=group_id)
    if group.cancelled:
        raise HttpError(409, "This group ride was cancelled")
    return group


def _online_out(row: LiveRider) -> dict:
    return {
        "user_id": row.user_id,
        "name": row.user.public_display_name,
        "status": row.status,
        "route": row.route,
        "mode": row.mode,
        "group_id": row.group_id,
    }


# -- Who is asking ---------------------------------------------------------


@router.get("/me", response=MeOut, auth=OptionalApiTokenAuth(), summary="Who the trainer page is riding for")
def me(request):
    user = request.auth if getattr(request.auth, "is_authenticated", False) else request.user
    if not getattr(user, "is_authenticated", False):
        return MeOut(authenticated=False, login_url=reverse("account_login"))
    return MeOut(
        authenticated=True,
        user_id=user.pk,
        name=user.public_display_name,
        profile_url=reverse("account_profile"),
    )


# -- Rides and records -----------------------------------------------------


@router.post("/rides", response={201: SavedRideOut}, auth=member_auth, summary="Save a finished ride")
def save_ride(request, payload: RideIn):
    data = payload.dict()
    group_id = data.pop("group_id")
    group = None
    if group_id is not None:
        group = get_object_or_404(GroupRide, pk=group_id)
        if not group.memberships.filter(user=request.auth).exists():
            raise HttpError(403, "You did not ride in this group race")
    with transaction.atomic():
        ride = VirtualRide.objects.create(user=request.auth, group=group, **data)
        found = records.new_records(request.auth, ride)
        if group is not None:
            records.rank_group(group)
            ride.refresh_from_db(fields=["place", "field_size"])
    return Status(201, SavedRideOut(ride=RideOut.from_orm(ride), records=found))


@router.get("/rides", response=list[RideOut], auth=member_auth, summary="My rides, newest first")
def list_rides(request, limit: int = 30):
    return list(VirtualRide.objects.filter(user=request.auth)[: max(1, min(limit, _MAX_HISTORY))])


@router.delete("/rides/{ride_id}", response={204: None}, auth=member_auth, summary="Delete one of my rides")
def delete_ride(request, ride_id: int):
    get_object_or_404(VirtualRide, pk=ride_id, user=request.auth).delete()
    return Status(204, None)


@router.get("/records", response=RecordsOut, auth=member_auth, summary="My personal records")
def my_records(request):
    return records.summary(request.auth)


# -- Group races -----------------------------------------------------------


@router.get("/groups", response=list[GroupOut], auth=member_auth, summary="Group races open to join")
def list_groups(request):
    return [_group_out(g, request.auth) for g in live.open_groups()]


@router.post("/groups", response={201: GroupOut}, auth=member_auth, summary="Gather a group race")
def create_group(request, payload: GroupIn):
    now = timezone.now()
    if GroupRide.objects.filter(host=request.auth, cancelled=False, start_at__gt=now).exists():
        raise HttpError(409, _("You already have a group race waiting to start"))
    with transaction.atomic():
        group = GroupRide.objects.create(
            route=payload.route,
            route_name=payload.route_name,
            host=request.auth,
            start_at=now + timedelta(seconds=payload.start_in_s),
        )
        GroupRideMember.objects.create(group=group, user=request.auth)
    return Status(201, _group_out(group, request.auth))


@router.post("/groups/{group_id}/join", response=GroupOut, auth=member_auth, summary="Join a group race")
def join_group(request, group_id: int):
    group = _open_group(group_id)
    if group.start_at <= timezone.now():
        raise HttpError(409, _("This group race has already started"))
    GroupRideMember.objects.get_or_create(group=group, user=request.auth)
    return _group_out(group, request.auth)


@router.post("/groups/{group_id}/leave", response=GroupOut, auth=member_auth, summary="Leave a group race")
def leave_group(request, group_id: int):
    group = _open_group(group_id)
    if group.host_id == request.auth.pk:
        raise HttpError(409, _("The host cancels the race instead of leaving it"))
    GroupRideMember.objects.filter(group=group, user=request.auth).delete()
    return _group_out(group, request.auth)


@router.post("/groups/{group_id}/cancel", response=GroupOut, auth=member_auth, summary="Cancel a group race")
def cancel_group(request, group_id: int):
    group = _open_group(group_id)
    if group.host_id != request.auth.pk and not is_admin(request.auth):
        raise HttpError(403, _("Only the host can cancel this group race"))
    group.cancelled = True
    group.save(update_fields=["cancelled"])
    return _group_out(group, request.auth)


@router.get("/groups/{group_id}/results", response=GroupResultsOut, auth=member_auth, summary="Group race results")
def group_results(request, group_id: int):
    group = get_object_or_404(GroupRide.objects.select_related("host"), pk=group_id)
    finished = [
        GroupResultOut(
            user_id=r.user_id, name=r.user.public_display_name, duration_s=r.duration_s, finished_at=r.finished_at
        )
        for r in records.group_results(group)
    ]
    return GroupResultsOut(group=_group_out(group, request.auth), finished=finished)


# -- Riding together -------------------------------------------------------


@router.post("/presence", response=PresenceOut, auth=member_auth, summary="Report my state, get the others back")
def presence(request, payload: PresenceIn):
    """Called by the trainer page about once a second while riding, every few seconds while setting up."""
    now = timezone.now()
    data = payload.dict()
    group_id = data.pop("group_id")
    group = None
    if group_id is not None:
        group = GroupRide.objects.filter(pk=group_id, cancelled=False, memberships__user=request.auth).first()
    me_row, _created = LiveRider.objects.update_or_create(
        user=request.auth, defaults={**data, "group": group, "updated_at": now}
    )
    riders = [
        RiderOut(
            **_online_out(row),
            distance_m=row.distance_m,
            speed_ms=row.speed_ms,
            cadence_rpm=row.cadence_rpm,
            power_w=row.power_w,
            lane_m=row.lane_m,
            finished_s=row.finished_s,
            age_s=max(0.0, (now - row.updated_at).total_seconds()),
        )
        for row in live.riders_beside(me_row, now).select_related("user")
    ]
    online_rows = live.online(now).exclude(user=request.auth)
    riding = me_row.status == LiveRider.Status.RIDE
    groups = [] if riding else [_group_out(g, request.auth) for g in live.open_groups(now)]
    online_out = [OnlineOut(**_online_out(r)) for r in online_rows]
    return PresenceOut(server_now=now, online=online_out, groups=groups, riders=riders)
