"""A member's intervals.icu: connected with their own API key, rides sent there as activities (#471).

intervals.icu takes HTTP Basic with the username ``API_KEY`` and the member's key as the password, and
reads the athlete id ``0`` as the key's own athlete (https://forum.intervals.icu/t/api-access-to-
intervals-icu/609). The key is checked when the member gives it and kept sealed
(``trainer.secret_box``); every call is made from the server, so it never reaches a page. Every call
goes through ``requests``, which the tests patch -- they never reach intervals.icu.
"""

import gzip
from datetime import date, timedelta
from http import HTTPStatus
from typing import Any

import requests
from django.core.cache import cache
from django.utils.html import strip_tags
from django.views.decorators.debug import sensitive_variables

from . import secret_box, strava, zwo
from .models import IntervalsConnection, IntervalsUpload, RideTrack, VirtualRide

API = "https://intervals.icu/api/v1"
# Saving a ride waits for the upload on one of the site's request threads: a slow intervals.icu fails
# it, and the member sends it again, rather than holding the thread
_TIMEOUT = 10
# marking a ride virtual is a nicety on top of an upload already made: it holds the save less long
_MARK_TIMEOUT = 5
# intervals.icu sits behind Cloudflare, which may challenge a library's own user agent
_HEADERS = {"User-Agent": "UniversalBicycleTeam/1.0 (+https://universalbicycle.team)", "Accept": "application/json"}
# Keys a member may try in a window: intervals.icu answers ten calls a second per address, and every try
# is one from the site's own, so one member trying keys in a loop would hold up everyone's uploads
_TRIES, _TRIES_WINDOW_S = 5, 10 * 60
# Reads of planned workouts a member may make in a window, for the same reason: each is one to three calls
_READS, _READS_WINDOW_S = 60, 10 * 60
# intervals.icu's activity types a bike rides: the planned workouts a trainer can take (its sport enum)
CYCLING = frozenset(
    "Ride VirtualRide MountainBikeRide GravelRide TrackRide Cyclocross EBikeRide EMountainBikeRide".split()
)
WORKOUT_DAYS = 8  # today and the next seven
_MAX_WORKOUTS = 50
_MAX_FTP = 1000


class IntervalsError(Exception):
    """intervals.icu refused or could not be reached; ``revoked`` when it no longer takes the key."""

    def __init__(self, message: str, revoked: bool = False):
        super().__init__(message)
        self.revoked = revoked


class TooManyTriesError(IntervalsError):
    """The member asked too often: held back here, before intervals.icu is asked again."""


class NotConnectedError(IntervalsError):
    """The member has no intervals.icu connection the site can use, or no longer has one."""


class NotFoundError(IntervalsError):
    """intervals.icu has no such planned workout for the member, or not one a bike rides."""


def available() -> bool:
    """The site can keep a member's key, so it offers intervals.icu."""
    return secret_box.available()


# every frame from here down, the HTTP library's too, holds the key: none of them goes into an error report
@sensitive_variables()
def _call(key: str, method: str, path: str, timeout: float = _TIMEOUT, accept: str = "", **kwargs) -> requests.Response:
    headers = {**_HEADERS, "Accept": accept} if accept else _HEADERS
    try:
        response = requests.request(
            method, f"{API}{path}", auth=("API_KEY", key), headers=headers, timeout=timeout, **kwargs
        )
    except requests.RequestException as exc:
        raise IntervalsError(f"intervals.icu could not be reached ({type(exc).__name__})") from None
    if response.status_code == HTTPStatus.UNAUTHORIZED:
        raise IntervalsError("intervals.icu does not accept this key", revoked=True)
    if response.status_code == HTTPStatus.FORBIDDEN:
        # not a verdict on the key: the proxy in front of intervals.icu turns an address away with 403 too,
        # and dropping every member's connection for it would be wrong
        raise IntervalsError("intervals.icu refused the request (403)")
    if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
        raise IntervalsError("intervals.icu asks to wait: too many requests")
    return response


def _body(response: requests.Response, kind: type = dict) -> Any:
    """The answer's JSON object (or list). Anything else -- a page from a proxy in front of it -- fails."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, kind):
        raise IntervalsError(f"intervals.icu answered {response.status_code} without its usual data")
    return body


def _allowed(user, what: str, tries: int, window_s: int) -> bool:
    """Count one more of ``what`` the member does; False past the window's allowance."""
    slot = f"intervals-{what}:{user.pk}"
    if cache.add(slot, 1, window_s):
        return True
    try:
        return cache.incr(slot) <= tries
    except ValueError:  # the window ran out between the two calls: this one opens a new one
        cache.add(slot, 1, window_s)
        return True


@sensitive_variables("key")
def connect(user, key: str, send_rides: bool = False) -> IntervalsConnection:
    """Check the key with intervals.icu, then keep it sealed with the athlete it belongs to."""
    key = key.strip()
    if not key:
        raise IntervalsError("No key given")
    if not _allowed(user, "connect-tries", _TRIES, _TRIES_WINDOW_S):
        raise TooManyTriesError("Too many tries: wait a few minutes before giving a key again")
    response = _call(key, "GET", "/athlete/0")
    if response.status_code != HTTPStatus.OK:
        raise IntervalsError(f"intervals.icu answered {response.status_code}")
    body = _body(response)
    athlete_id = str(body.get("id") or "")[:40]
    if not athlete_id:
        raise IntervalsError("intervals.icu named no athlete for this key")
    connection, _created = IntervalsConnection.objects.update_or_create(
        user=user,
        defaults={
            "athlete_id": athlete_id,
            "athlete_name": str(body.get("name") or "")[:120],
            "api_key": secret_box.seal(key),
            "send_rides": send_rides,
        },
    )
    return connection


def disconnect(connection: IntervalsConnection) -> None:
    """Forget the key: it is the member's own, to keep or regenerate at intervals.icu."""
    connection.delete()


def _record(ride: VirtualRide, status: str, error: str = "", activity_id: str = "") -> IntervalsUpload:
    record, _created = IntervalsUpload.objects.update_or_create(
        ride=ride, defaults={"status": status, "error": strip_tags(error)[:300], "activity_id": activity_id[:40]}
    )
    return record


@sensitive_variables("key")
def upload(ride: VirtualRide) -> IntervalsUpload:
    """Send one ride to the member's intervals.icu as an activity. A failure is recorded, not raised."""
    failed = IntervalsUpload.Status.FAILED
    connection = IntervalsConnection.objects.filter(user_id=ride.user_id).first()
    track = RideTrack.objects.filter(ride=ride).first()
    if connection is None or track is None:
        return _record(
            ride, failed, "Not connected to intervals.icu" if connection is None else "The ride has no track"
        )
    key = secret_box.open_sealed(connection.api_key)
    if key is None:
        # the site's key changed or was lost: the member gives theirs again
        connection.delete()
        return _record(ride, failed, "The intervals.icu key can no longer be read: connect intervals.icu again")
    params = {
        "name": ride.route_name or ride.route,
        "external_id": f"universalbicycle-virtual-ride-{ride.pk}",
        "device_name": "Universal Bicycle Team virtual ride",
    }
    # the TCX Strava gets, unpacked: intervals.icu does not document taking it gzipped
    files = {
        "file": (f"virtual-ride-{ride.pk}.tcx", gzip.decompress(strava.tcx(ride, track.points)), "application/xml")
    }
    try:
        response = _call(key, "POST", f"/athlete/{connection.athlete_id}/activities", params=params, files=files)
        if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
            return _record(ride, failed, response.text or f"intervals.icu answered {response.status_code}")
        body = _body(response)
    except IntervalsError as exc:
        if exc.revoked:
            connection.delete()
        return _record(ride, failed, str(exc))
    activities = body.get("activities") or [{}]
    activity_id = str(body.get("id") or activities[0].get("id") or "")
    if not activity_id:
        return _record(ride, failed, "intervals.icu named no activity for the ride")
    _mark_virtual(key, activity_id)
    return _record(ride, IntervalsUpload.Status.DONE, activity_id=activity_id)


@sensitive_variables("key")
def _mark_virtual(key: str, activity_id: str) -> None:
    """A TCX reads as a ride on the road; this one was on a trainer in a virtual world.

    Best effort: the ride is on intervals.icu either way, so a refusal here is let go.
    """
    try:
        _call(
            key, "PUT", f"/activity/{activity_id}", timeout=_MARK_TIMEOUT, json={"type": "VirtualRide", "trainer": True}
        )
    except IntervalsError:
        pass


# -- Planned workouts (phase 2) ---------------------------------------------


@sensitive_variables("key")
def _member(user) -> tuple[IntervalsConnection, str]:
    """The member's connection and key, read at most ``_READS`` times a window."""
    if not _allowed(user, "reads", _READS, _READS_WINDOW_S):
        raise TooManyTriesError("Too many requests for workouts: wait a few minutes")
    connection = IntervalsConnection.objects.filter(user=user).first()
    if connection is None:
        raise NotConnectedError("Connect intervals.icu in your profile first")
    key = secret_box.open_sealed(connection.api_key)
    if key is None:
        connection.delete()  # the site's key changed or was lost: the member gives theirs again
        raise NotConnectedError("The intervals.icu key can no longer be read: connect intervals.icu again")
    return connection, key


@sensitive_variables("key")
def _get(connection: IntervalsConnection, key: str, path: str, **kwargs) -> requests.Response:
    """A read with the member's key. A key intervals.icu no longer takes drops the connection, as an upload does."""
    try:
        response = _call(key, "GET", path, **kwargs)
    except IntervalsError as exc:
        if exc.revoked:
            connection.delete()
            raise NotConnectedError("intervals.icu no longer accepts your key: connect intervals.icu again") from None
        raise
    if response.status_code == HTTPStatus.NOT_FOUND:
        raise NotFoundError("intervals.icu has no such workout")
    if response.status_code != HTTPStatus.OK:
        raise IntervalsError(f"intervals.icu answered {response.status_code}")
    return response


def _listed(event) -> dict | None:
    """A planned workout as the trainer page lists it, or None for one a bike does not ride."""
    if not isinstance(event, dict) or event.get("type") not in CYCLING:
        return None
    try:
        event_id = int(event["id"])
    except (KeyError, TypeError, ValueError):
        return None
    moving = event.get("moving_time")
    return {
        "id": event_id,
        "date": str(event.get("start_date_local") or "")[:10],
        "name": str(event.get("name") or "")[:120],
        "duration_s": moving if isinstance(moving, int) and 0 < moving <= zwo.MAX_SECONDS * 4 else None,
    }


@sensitive_variables("key")
def planned_workouts(user, oldest: date) -> list[dict]:
    """The cycling workouts planned in the member's intervals.icu calendar, from ``oldest`` for eight days."""
    connection, key = _member(user)
    params = {
        "oldest": oldest.isoformat(),
        "newest": (oldest + timedelta(days=WORKOUT_DAYS - 1)).isoformat(),
        "category": "WORKOUT",
    }
    events = _body(_get(connection, key, f"/athlete/{connection.athlete_id}/events", params=params), list)
    listed = [row for row in map(_listed, events) if row]
    return sorted(listed, key=lambda row: row["date"])[:_MAX_WORKOUTS]


def _ftp(value) -> int | None:
    return value if isinstance(value, int) and 0 < value <= _MAX_FTP else None


@sensitive_variables("key")
def _ride_ftp(connection: IntervalsConnection, key: str) -> int | None:
    """The FTP of the member's ride settings in intervals.icu: the indoor one first, a trainer being indoors."""
    athlete = _body(_get(connection, key, f"/athlete/{connection.athlete_id}"))
    for sport in athlete.get("sportSettings") or []:
        types = sport.get("types") if isinstance(sport, dict) else None
        if isinstance(types, list) and any(isinstance(kind, str) and kind in CYCLING for kind in types):
            return _ftp(sport.get("indoor_ftp")) or _ftp(sport.get("ftp"))
    return None


@sensitive_variables("key")
def planned_workout(user, event_id: int) -> dict:
    """One planned workout: its steps and cues, the power in watts from the FTP intervals.icu gives it.

    Nothing of it is kept: FTP, zones and the workout stay in intervals.icu.
    """
    connection, key = _member(user)
    path = f"/athlete/{connection.athlete_id}/events/{event_id}"
    event = _body(_get(connection, key, path))
    listed = _listed(event)
    if listed is None or event.get("category") != "WORKOUT":
        raise NotFoundError("This is not a cycling workout")
    ftp = _ftp(event.get("icu_ftp")) or _ride_ftp(connection, key)
    file = _get(connection, key, f"{path}/download.zwo", accept="*/*")  # a file, not JSON
    try:
        steps = zwo.parse(file.content, ftp)
    except zwo.NoFtpError:
        raise IntervalsError("intervals.icu gives no FTP for your rides: set it there to ride this workout") from None
    except zwo.ZwoError as exc:
        raise IntervalsError(str(exc)) from None
    return {**listed, "ftp_w": ftp, **steps}
