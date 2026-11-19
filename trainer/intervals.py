"""A member's intervals.icu: connected with their own API key, rides sent there as activities (#471).

intervals.icu takes HTTP Basic with the username ``API_KEY`` and the member's key as the password, and
reads the athlete id ``0`` as the key's own athlete (https://forum.intervals.icu/t/api-access-to-
intervals-icu/609). The key is checked when the member gives it and kept sealed
(``trainer.secret_box``); every call is made from the server, so it never reaches a page. Every call
goes through ``requests``, which the tests patch -- they never reach intervals.icu.
"""

import gzip
from http import HTTPStatus

import requests
from django.utils.html import strip_tags

from . import secret_box, strava
from .models import IntervalsConnection, IntervalsUpload, RideTrack, VirtualRide

API = "https://intervals.icu/api/v1"
# Saving a ride waits for the upload on one of the site's request threads: a slow intervals.icu fails
# it, and the member sends it again, rather than holding the thread
_TIMEOUT = 10
# intervals.icu sits behind Cloudflare, which may challenge a library's own user agent
_HEADERS = {"User-Agent": "UniversalBicycleTeam/1.0 (+https://universalbicycle.team)", "Accept": "application/json"}
_REFUSED = (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)


class IntervalsError(Exception):
    """intervals.icu refused or could not be reached; ``revoked`` when it no longer takes the key."""

    def __init__(self, message: str, revoked: bool = False):
        super().__init__(message)
        self.revoked = revoked


def available() -> bool:
    """The site can keep a member's key, so it offers intervals.icu."""
    return secret_box.available()


def _call(key: str, method: str, path: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(
            method, f"{API}{path}", auth=("API_KEY", key), headers=_HEADERS, timeout=_TIMEOUT, **kwargs
        )
    except requests.RequestException as exc:
        raise IntervalsError(f"intervals.icu could not be reached ({type(exc).__name__})") from None
    if response.status_code in _REFUSED:
        raise IntervalsError("intervals.icu does not accept this key", revoked=True)
    if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
        raise IntervalsError("intervals.icu asks to wait: too many requests")
    return response


def connect(user, key: str, send_rides: bool = False) -> IntervalsConnection:
    """Check the key with intervals.icu, then keep it sealed with the athlete it belongs to."""
    key = key.strip()
    if not key:
        raise IntervalsError("No key given")
    response = _call(key, "GET", "/athlete/0")
    if response.status_code != HTTPStatus.OK:
        raise IntervalsError(f"intervals.icu answered {response.status_code}")
    body = response.json()
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
    except IntervalsError as exc:
        if exc.revoked:
            connection.delete()
        return _record(ride, failed, str(exc))
    if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
        return _record(ride, failed, response.text or f"intervals.icu answered {response.status_code}")
    body = response.json()
    activities = body.get("activities") or [{}]
    activity_id = str(body.get("id") or activities[0].get("id") or "")
    if not activity_id:
        return _record(ride, failed, "intervals.icu named no activity for the ride")
    _mark_virtual(key, activity_id)
    return _record(ride, IntervalsUpload.Status.DONE, activity_id=activity_id)


def _mark_virtual(key: str, activity_id: str) -> None:
    """A TCX reads as a ride on the road; this one was on a trainer in a virtual world.

    Best effort: the ride is on intervals.icu either way, so a refusal here is let go.
    """
    try:
        _call(key, "PUT", f"/activity/{activity_id}", json={"type": "VirtualRide", "trainer": True})
    except IntervalsError:
        pass
