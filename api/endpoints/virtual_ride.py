"""Virtual ride: a member's saved rides and records, group races, and riding together.

The trainer page (trainer/static/trainer/alatau.html) calls these from the member's browser with
their session; API clients use the personal Bearer token like everywhere else in /api/v1/.
"""

import contextlib
import json
from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from ninja import Field, Path, Router, Schema, Status
from ninja.errors import HttpError
from pydantic import SecretStr, field_validator

from accounts import roles
from accounts.access import needs_email_confirmation
from api.auth import OptionalApiTokenAuth, member_auth
from trainer import intervals, live, records, services, strava
from trainer.models import (
    GroupRide,
    GroupRideMember,
    IntervalsConnection,
    IntervalsUpload,
    LiveRider,
    RideTrack,
    StravaConnection,
    StravaUpload,
    TrainerSettings,
    VirtualRide,
)

router = Router(tags=["virtual-ride"])


_ROUTE = r"^[a-z0-9][a-z0-9_-]{0,39}$"
# The strongest wind a ride or a group race is ridden in, m/s: a storm
_MAX_WIND_MS = 30
_MAX_HISTORY = 100
# The trainer page's settings, as JSON: a long own plan is a few kilobytes
_MAX_SETTINGS = 64 * 1024
# One point a second for six hours; each point is
# [t_s, lat, lon, ele_m, distance_m, speed_ms, power_w, cadence_rpm, hr_bpm] within these bounds.
_MAX_TRACK = 6 * 3600
_TRACK_BOUNDS = (
    (0, 24 * 3600),
    (-90, 90),
    (-180, 180),
    (-500, 9000),
    (0, 1_000_000),
    (0, 40),
    (0, 3000),
    (0, 250),
    (0, 260),
)


# -- Schemas ---------------------------------------------------------------


class MeOut(Schema):
    authenticated: bool
    user_id: int | None = None
    name: str = ""
    profile_url: str = ""
    login_url: str = ""
    # the site's page that frames the trainer: where a shared link to a group race should lead
    page_url: str = ""
    # Sending rides to Strava: whether the site can, whether this member turned it on, where to turn it on
    strava_available: bool = False
    strava_connected: bool = False
    strava_athlete: str = ""
    strava_connect_url: str = ""
    # whether the member's box sends their rides there (issue #471)
    strava_send: bool = False
    intervals_available: bool = False
    intervals_connected: bool = False
    intervals_athlete: str = ""
    intervals_send: bool = False


class TrainerSettingsIn(Schema):
    # the page's own object, kept as it comes; base is the account's stamp of the copy the page last had (0: none)
    settings: dict[str, Any]
    base: int = Field(ge=0, le=10**15)


class TrainerSettingsOut(Schema):
    settings: dict[str, Any]
    # the site's clock, in ms, when the copy kept was saved; 0 while nothing is kept
    saved_at: int


class TrainerSettingsKeptOut(TrainerSettingsOut):
    # whether the page's copy was kept, or another device's later one stands and comes back instead
    accepted: bool


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
    track: list[list[float]] | None = Field(None, max_length=_MAX_TRACK)
    wind_ms: float = Field(0, ge=0, le=_MAX_WIND_MS)
    wind_from_deg: int = Field(0, ge=0, le=359)

    @field_validator("track")
    @classmethod
    def _track_points(cls, track):
        for point in track or []:
            if len(point) != len(_TRACK_BOUNDS) or not all(
                lo <= v <= hi for v, (lo, hi) in zip(point, _TRACK_BOUNDS, strict=True)
            ):
                raise ValueError(
                    "each track point is [t_s, lat, lon, ele_m, distance_m, speed_ms, power_w, cadence_rpm, hr_bpm]"
                    " within their bounds"
                )
        return track


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
    wind_ms: float
    wind_from_deg: int


class StravaOut(Schema):
    status: str
    activity_url: str = ""
    error: str = ""


class IntervalsOut(Schema):
    status: str
    activity_url: str = ""
    error: str = ""


class SavedRideOut(Schema):
    ride: RideOut
    records: list[str]
    strava: StravaOut | None = None
    intervals: IntervalsOut | None = None


class ServiceOut(Schema):
    available: bool
    connected: bool
    athlete: str = ""
    send_rides: bool = False


class ServicesOut(Schema):
    strava: ServiceOut
    intervals: ServiceOut
    # where a browser starts the Strava round trip; intervals.icu is connected with a key instead
    strava_connect_url: str = ""


class SendIn(Schema):
    send_rides: bool


class IntervalsConnectIn(Schema):
    # secret: shown as stars wherever the payload is printed, an error report's frames too
    api_key: SecretStr = Field(..., min_length=1, max_length=200)
    send_rides: bool = False


class PlannedWorkoutOut(Schema):
    id: int
    # the day it is planned for, in the member's own calendar at intervals.icu (YYYY-MM-DD)
    date: str
    name: str
    duration_s: int | None = None


class WorkoutStepOut(Schema):
    duration_s: int
    # the power at the step's start and at its end, in watts: equal for a steady step, none for a free one
    power_w: int | None = None
    power_end_w: int | None = None
    cadence_rpm: int | None = None


class WorkoutCueOut(Schema):
    # seconds from the workout's start
    at_s: int
    text: str


class WorkoutOut(PlannedWorkoutOut):
    # the FTP intervals.icu gives the workout, which its shares of FTP were turned into watts with
    ftp_w: int | None = None
    steps: list[WorkoutStepOut]
    cues: list[WorkoutCueOut]


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
    cancelled: bool = False
    wind_ms: float = 0
    wind_from_deg: int = 0


class GroupIn(Schema):
    route: str = Field(..., pattern=_ROUTE, max_length=40)
    route_name: str = Field("", max_length=120)
    # the start: so many seconds from now, or at a moment with its time zone, up to a year ahead
    start_in_s: int = Field(60, ge=live.MIN_START_DELAY_S, le=live.MAX_START_DELAY_S)
    start_at: datetime | None = None
    wind_ms: float = Field(0, ge=0, le=_MAX_WIND_MS)
    wind_from_deg: int = Field(0, ge=0, le=359)


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
        cancelled=group.cancelled,
        wind_ms=group.wind_ms,
        wind_from_deg=group.wind_from_deg,
    )


def _open_group(group_id: int) -> GroupRide:
    group = get_object_or_404(GroupRide.objects.select_related("host"), pk=group_id)
    if group.cancelled:
        raise HttpError(HTTPStatus.CONFLICT, "This group ride was cancelled")
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


def _in_page_language(request):
    """The language of the page the trainer runs in, which it names on every call (X-Page-Language), for what a
    ride takes out in words: the invitation on Strava and intervals.icu. A profile's own choice still comes first
    (trainer/invitation.py); without the header, the request's language stands."""
    code = request.headers.get("X-Page-Language", "")
    try:
        return (
            translation.override(translation.get_supported_language_variant(code)) if code else contextlib.nullcontext()
        )
    except LookupError:
        return contextlib.nullcontext()


# -- Who is asking ---------------------------------------------------------


@router.get("/me", response=MeOut, auth=OptionalApiTokenAuth(), summary="Who the trainer page is riding for")
def me(request):
    user = request.auth if request.auth.is_authenticated else request.user
    if not user.is_authenticated or needs_email_confirmation(user):
        return MeOut(authenticated=False, login_url=reverse("account_login"), page_url=reverse("virtual_ride"))
    connection = StravaConnection.objects.filter(user=user).first()
    sent = services.state(user)
    return MeOut(
        authenticated=True,
        user_id=user.pk,
        name=user.public_display_name,
        profile_url=reverse("account_profile"),
        page_url=reverse("virtual_ride"),
        strava_available=strava.available(),
        strava_connected=connection is not None,
        strava_athlete=connection.athlete_name if connection else "",
        strava_connect_url=reverse("virtual_ride_strava_connect") if strava.available() else "",
        strava_send=sent[services.STRAVA]["send_rides"],
        intervals_available=sent[services.INTERVALS]["available"],
        intervals_connected=sent[services.INTERVALS]["connected"],
        intervals_athlete=sent[services.INTERVALS]["athlete"],
        intervals_send=sent[services.INTERVALS]["send_rides"],
    )


# -- Rides and records -----------------------------------------------------


@router.post("/rides", response={HTTPStatus.CREATED: SavedRideOut}, auth=member_auth, summary="Save a finished ride")
def save_ride(request, payload: RideIn):
    data = payload.dict()
    group_id = data.pop("group_id")
    track = data.pop("track")
    group = None
    if group_id is not None:
        group = get_object_or_404(GroupRide, pk=group_id)
        if not group.memberships.filter(user=request.auth).exists():
            raise HttpError(HTTPStatus.FORBIDDEN, "You did not ride in this group race")
    with transaction.atomic():
        if group is not None:
            # Members finishing together take turns, so each ranking sees the rides saved before it.
            group = GroupRide.objects.select_for_update().get(pk=group.pk)
        ride = VirtualRide.objects.create(user=request.auth, group=group, **data)
        if track:
            RideTrack.objects.create(ride=ride, points=track)
        found = records.new_records(request.auth, ride)
        if group is not None:
            records.rank_group(group)
            ride.refresh_from_db(fields=["place", "field_size"])
    # every service the member connected with its box on gets the ride; demo power is not a ride to show
    with _in_page_language(request):
        to_strava, to_intervals = services.send_saved(ride)
    return Status(
        HTTPStatus.CREATED,
        SavedRideOut(
            ride=RideOut.from_orm(ride),
            records=found,
            strava=_strava_out(to_strava) if to_strava else None,
            intervals=_intervals_out(to_intervals) if to_intervals else None,
        ),
    )


def _strava_on(user) -> bool:
    return strava.available() and StravaConnection.objects.filter(user=user).exists()


def _strava_out(upload: StravaUpload) -> StravaOut:
    return StravaOut(status=upload.status, activity_url=upload.activity_url, error=upload.error)


@router.post("/rides/{ride_id}/strava", response=StravaOut, auth=member_auth, summary="Send one of my rides to Strava")
def send_to_strava(request, ride_id: int):
    """Again after a failure, or a ride saved before Strava was connected: it goes as a Virtual Ride."""
    ride = get_object_or_404(VirtualRide, pk=ride_id, user=request.auth)
    sent = StravaUpload.objects.filter(ride=ride).first()
    if sent is not None and sent.status != StravaUpload.Status.FAILED:
        # on Strava already, or on its way: sending it again would only come back a duplicate
        return _strava_out(strava.refresh(sent))
    if not _strava_on(request.auth):
        raise HttpError(HTTPStatus.CONFLICT, _("Connect Strava in your profile first"))
    if not services.sendable(ride):
        raise HttpError(
            HTTPStatus.CONFLICT,
            _("This ride has no track to send: rides in demo mode and rides saved without one stay here"),
        )
    with _in_page_language(request):
        return _strava_out(strava.upload(ride))


@router.get("/rides/{ride_id}/strava", response=StravaOut, auth=member_auth, summary="How my ride's Strava upload went")
def strava_status(request, ride_id: int):
    upload = get_object_or_404(StravaUpload.objects.select_related("ride"), ride_id=ride_id, ride__user=request.auth)
    return _strava_out(strava.refresh(upload))


def _intervals_out(upload: IntervalsUpload) -> IntervalsOut:
    return IntervalsOut(status=upload.status, activity_url=upload.activity_url, error=upload.error)


@router.post(
    "/rides/{ride_id}/intervals",
    response=IntervalsOut,
    auth=member_auth,
    summary="Send one of my rides to intervals.icu",
)
def send_to_intervals(request, ride_id: int):
    """Again after a failure, or a ride saved before intervals.icu was connected or its box turned on."""
    ride = get_object_or_404(VirtualRide, pk=ride_id, user=request.auth)
    sent = IntervalsUpload.objects.filter(ride=ride).first()
    if sent is not None and sent.status == IntervalsUpload.Status.DONE:
        return _intervals_out(sent)  # there already: sending it again would only make a second activity
    if not (intervals.available() and IntervalsConnection.objects.filter(user=request.auth).exists()):
        raise HttpError(HTTPStatus.CONFLICT, _("Connect intervals.icu in your profile first"))
    if not services.sendable(ride):
        raise HttpError(
            HTTPStatus.CONFLICT,
            _("This ride has no track to send: rides in demo mode and rides saved without one stay here"),
        )
    with _in_page_language(request):
        return _intervals_out(intervals.upload(ride))


@router.get(
    "/rides/{ride_id}/intervals",
    response=IntervalsOut,
    auth=member_auth,
    summary="How my ride's intervals.icu upload went",
)
def intervals_status(request, ride_id: int):
    return _intervals_out(get_object_or_404(IntervalsUpload, ride_id=ride_id, ride__user=request.auth))


# -- Where my rides go -----------------------------------------------------


def _services_out(user) -> ServicesOut:
    sent = services.state(user)
    return ServicesOut(
        strava=ServiceOut(**sent[services.STRAVA]),
        intervals=ServiceOut(**sent[services.INTERVALS]),
        strava_connect_url=reverse("virtual_ride_strava_connect") if strava.available() else "",
    )


@router.get("/services", response=ServicesOut, auth=member_auth, summary="Where my rides go")
def my_services(request):
    return _services_out(request.auth)


def _sending(request, service: str, payload: SendIn) -> ServicesOut:
    if not services.set_sending(request.auth, service, payload.send_rides):
        raise HttpError(HTTPStatus.CONFLICT, _("Connect the service in your profile first"))
    return _services_out(request.auth)


# One path per service, not "/services/{service}": a pattern would take POST and DELETE on
# /services/intervals too, and answer them 405
@router.patch("/services/strava", response=ServicesOut, auth=member_auth, summary="Send my rides to Strava, or not")
def set_strava_sending(request, payload: SendIn):
    return _sending(request, services.STRAVA, payload)


@router.patch(
    "/services/intervals", response=ServicesOut, auth=member_auth, summary="Send my rides to intervals.icu, or not"
)
def set_intervals_sending(request, payload: SendIn):
    return _sending(request, services.INTERVALS, payload)


@router.post(
    "/services/intervals",
    response={HTTPStatus.CREATED: ServicesOut},
    auth=member_auth,
    summary="Connect my intervals.icu with my API key",
)
def connect_intervals(request, payload: IntervalsConnectIn):
    """The key is checked with intervals.icu, then kept sealed; it is never given back."""
    if not intervals.available():
        raise HttpError(HTTPStatus.CONFLICT, _("intervals.icu is not offered on this site"))
    try:
        intervals.connect(request.auth, payload.api_key.get_secret_value(), payload.send_rides)
    except intervals.TooManyTriesError as exc:
        raise HttpError(HTTPStatus.TOO_MANY_REQUESTS, str(exc)) from None
    except intervals.IntervalsError as exc:
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from None
    return Status(HTTPStatus.CREATED, _services_out(request.auth))


@router.delete(
    "/services/intervals",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Disconnect my intervals.icu",
)
def disconnect_intervals(request):
    connection = IntervalsConnection.objects.filter(user=request.auth).first()
    if connection is not None:
        intervals.disconnect(connection)
    return Status(HTTPStatus.NO_CONTENT, None)


def _from_intervals(read):
    """A read of the member's intervals.icu, its failures as the API answers them."""
    if not intervals.available():
        raise HttpError(HTTPStatus.CONFLICT, _("intervals.icu is not offered on this site"))
    try:
        return read()
    except intervals.NotConnectedError as exc:
        raise HttpError(HTTPStatus.CONFLICT, str(exc)) from None
    except intervals.NotFoundError as exc:
        raise HttpError(HTTPStatus.NOT_FOUND, str(exc)) from None
    except intervals.NotRideableError as exc:  # no steps, or power without an FTP: trying again changes nothing
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from None
    except intervals.TooManyTriesError as exc:
        raise HttpError(HTTPStatus.TOO_MANY_REQUESTS, str(exc)) from None
    except intervals.IntervalsError as exc:
        raise HttpError(HTTPStatus.SERVICE_UNAVAILABLE, str(exc)) from None


@router.get(
    "/intervals/workouts",
    response=list[PlannedWorkoutOut],
    auth=member_auth,
    summary="My cycling workouts planned in intervals.icu, for eight days",
)
def planned_workouts(request, oldest: date | None = None):
    """From ``oldest`` (the trainer page sends the rider's own today; the site's by default) for eight days."""
    first = oldest or timezone.localdate()
    return _from_intervals(lambda: intervals.planned_workouts(request.auth, first))


@router.get(
    "/intervals/workouts/{event_id}",
    response=WorkoutOut,
    auth=member_auth,
    summary="One of my planned workouts: its steps, the power in watts",
)
def planned_workout(request, event_id: int = Path(..., ge=1, le=2**31 - 1)):  # intervals.icu's ids are int32
    """Read from intervals.icu each time: the site keeps neither the workout nor the FTP."""
    return _from_intervals(lambda: intervals.planned_workout(request.auth, event_id))


@router.delete(
    "/strava", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Stop sending my rides to Strava"
)
def disconnect_strava(request):
    connection = StravaConnection.objects.filter(user=request.auth).first()
    if connection is not None:
        strava.disconnect(connection)
    return Status(HTTPStatus.NO_CONTENT, None)


@router.get("/rides", response=list[RideOut], auth=member_auth, summary="My rides, newest first")
def list_rides(request, limit: int = 30):
    return list(VirtualRide.objects.filter(user=request.auth)[: max(1, min(limit, _MAX_HISTORY))])


@router.delete(
    "/rides/{ride_id}", response={HTTPStatus.NO_CONTENT: None}, auth=member_auth, summary="Delete one of my rides"
)
def delete_ride(request, ride_id: int):
    ride = get_object_or_404(VirtualRide, pk=ride_id, user=request.auth)
    with transaction.atomic():
        # a group race's places come from its saved rides: one gone, the others move up
        group = GroupRide.objects.select_for_update().get(pk=ride.group_id) if ride.group_id else None
        ride.delete()
        if group is not None:
            records.rank_group(group)
    return Status(HTTPStatus.NO_CONTENT, None)


@router.get("/records", response=RecordsOut, auth=member_auth, summary="My personal records")
def my_records(request):
    return records.summary(request.auth)


# -- Settings --------------------------------------------------------------


@router.get("/settings", response=TrainerSettingsOut, auth=member_auth, summary="My settings on the trainer page")
def my_settings(request):
    kept = TrainerSettings.objects.filter(user=request.auth).first()
    return TrainerSettingsOut(settings=kept.data if kept else {}, saved_at=kept.saved_at if kept else 0)


@router.put(
    "/settings", response=TrainerSettingsKeptOut, auth=member_auth, summary="Keep my settings on the trainer page"
)
def keep_settings(request, payload: TrainerSettingsIn):
    """The page's settings with the member's account, stamped by the site's clock, never a device's own.

    A page that had the latest copy (``base``) replaces it; one that was behind -- another device saved
    since -- is handed that copy instead, and takes it.
    """
    if len(json.dumps(payload.settings)) > _MAX_SETTINGS:
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "The settings are too large to keep")
    with transaction.atomic():
        kept, _created = TrainerSettings.objects.select_for_update().get_or_create(user=request.auth)
        accepted = payload.base >= kept.saved_at
        if accepted:
            now = int(timezone.now().timestamp() * 1000)
            kept.data, kept.saved_at = payload.settings, max(now, kept.saved_at + 1)
            kept.save(update_fields=["data", "saved_at", "updated_at"])
    return TrainerSettingsKeptOut(settings=kept.data, saved_at=kept.saved_at, accepted=accepted)


# -- Group races -----------------------------------------------------------


@router.get("/groups", response=list[GroupOut], auth=member_auth, summary="Group races open to join")
def list_groups(request):
    return [_group_out(g, request.auth) for g in live.open_groups()]


@router.post("/groups", response={HTTPStatus.CREATED: GroupOut}, auth=member_auth, summary="Gather a group race")
def create_group(request, payload: GroupIn):
    """A race on a route: starting in so many seconds, or at a date and time up to a year ahead. A host's races start
    an hour apart at least, as a rider rides one at a time."""
    now = timezone.now()
    start = payload.start_at or now + timedelta(seconds=payload.start_in_s)
    if timezone.is_naive(start):
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, _("A start needs its time zone"))
    if not now + timedelta(seconds=live.MIN_START_DELAY_S) <= start <= now + live.MAX_AHEAD:
        soonest = {"seconds": live.MIN_START_DELAY_S}
        raise HttpError(
            HTTPStatus.UNPROCESSABLE_ENTITY, _("A group race starts %(seconds)d seconds to a year from now") % soonest
        )
    mine = GroupRide.objects.filter(host=request.auth, cancelled=False, start_at__gt=now)
    if mine.filter(start_at__gt=start - live.RACE_GAP, start_at__lt=start + live.RACE_GAP).exists():
        raise HttpError(HTTPStatus.CONFLICT, _("You already have a group race starting within an hour of that time"))
    with transaction.atomic():
        group = GroupRide.objects.create(
            route=payload.route,
            route_name=payload.route_name,
            host=request.auth,
            start_at=start,
            wind_ms=payload.wind_ms,
            wind_from_deg=payload.wind_from_deg,
        )
        GroupRideMember.objects.create(group=group, user=request.auth)
    return Status(HTTPStatus.CREATED, _group_out(group, request.auth))


@router.get("/groups/{group_id}", response=GroupOut, auth=member_auth, summary="One group race, as a link names it")
def get_group(request, group_id: int):
    """What a shared link opens: the race even when it has started or was cancelled, so the page can say so."""
    group = get_object_or_404(GroupRide.objects.select_related("host"), pk=group_id)
    return _group_out(group, request.auth)


@router.post("/groups/{group_id}/join", response=GroupOut, auth=member_auth, summary="Join a group race")
def join_group(request, group_id: int):
    group = _open_group(group_id)
    if group.start_at <= timezone.now():
        raise HttpError(HTTPStatus.CONFLICT, _("This group race has already started"))
    GroupRideMember.objects.get_or_create(group=group, user=request.auth)
    return _group_out(group, request.auth)


@router.post("/groups/{group_id}/leave", response=GroupOut, auth=member_auth, summary="Leave a group race")
def leave_group(request, group_id: int):
    """A host who leaves hands the race to the rider who joined next; alone in it, they cancel it."""
    _open_group(group_id)
    with transaction.atomic():
        group = GroupRide.objects.select_for_update().get(pk=group_id)
        GroupRideMember.objects.filter(group=group, user=request.auth).delete()
        if group.host_id == request.auth.pk:
            heir = group.memberships.order_by("joined_at", "pk").first()
            if heir is None:
                group.cancelled = True
            else:
                group.host_id = heir.user_id
            group.save(update_fields=["cancelled", "host"])
    return _group_out(GroupRide.objects.select_related("host").get(pk=group_id), request.auth)


@router.post("/groups/{group_id}/cancel", response=GroupOut, auth=member_auth, summary="Cancel a group race")
def cancel_group(request, group_id: int):
    group = _open_group(group_id)
    if group.host_id != request.auth.pk and not roles.at_least(request.auth, roles.Role.ADMIN):
        raise HttpError(HTTPStatus.FORBIDDEN, _("Only the host can cancel this group race"))
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
