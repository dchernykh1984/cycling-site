"""Sending a member's virtual rides to Strava as Virtual Ride activities.

Signing in with Strava asks for ``read`` only and keeps no token (``specs/site/accounts.md``,
FR-ACC-007). Uploading needs ``activity:write``: the member grants it separately from the profile, its
tokens live in ``StravaConnection`` and are refreshed here when they expire. Every call goes through
``requests``, which the tests patch -- they never reach Strava.
"""

import gzip
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags

from .models import RideTrack, StravaConnection, StravaUpload, VirtualRide

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"  # noqa: S105 -- an address, not a secret
DEAUTHORIZE_URL = "https://www.strava.com/oauth/deauthorize"
UPLOADS_URL = "https://www.strava.com/api/v3/uploads"
# "read" keeps the athlete's name in the token answer; "activity:write" is what uploading needs
SCOPE = "read,activity:write"
# Saving a ride waits for Strava (a token refresh, then the upload) on one of the site's four request
# threads: a slow Strava fails the upload, which can be sent again, rather than hold the thread
_TIMEOUT = 10
_TCX = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_TPX = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
ET.register_namespace("", _TCX)
ET.register_namespace("tpx", _TPX)


class StravaError(Exception):
    """Strava refused or could not be reached; ``revoked`` when the member's grant no longer works."""

    def __init__(self, message: str, revoked: bool = False):
        super().__init__(message)
        self.revoked = revoked


def _app() -> dict:
    return cast(dict, settings.SOCIALACCOUNT_PROVIDERS["strava"]["APP"])


def available() -> bool:
    """The site has a Strava application to upload with."""
    app = _app()
    return bool(app.get("client_id") and app.get("secret"))


def authorize_url(redirect_uri: str, state: str) -> str:
    query = {
        "client_id": _app()["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _when(epoch) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=UTC)


def _token(**data) -> dict:
    app = _app()
    try:
        response = requests.post(
            TOKEN_URL, data={"client_id": app["client_id"], "client_secret": app["secret"], **data}, timeout=_TIMEOUT
        )
    except requests.RequestException as exc:
        raise StravaError(type(exc).__name__) from None
    if response.status_code != 200:
        # a code or refresh token Strava no longer accepts: the member revoked the grant or never gave it
        raise StravaError(f"Strava answered {response.status_code}", revoked=response.status_code in (400, 401))
    return response.json()


def connect(user, code: str) -> StravaConnection:
    """Trade the code Strava sent back for tokens and keep them for this member."""
    data = _token(code=code, grant_type="authorization_code")
    athlete = data.get("athlete") or {}
    name = " ".join(part for part in (athlete.get("firstname"), athlete.get("lastname")) if part)
    connection, _created = StravaConnection.objects.update_or_create(
        user=user,
        defaults={
            "athlete_id": athlete.get("id") or 0,
            "athlete_name": name[:120],
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": _when(data["expires_at"]),
        },
    )
    return connection


def _access_token(connection: StravaConnection) -> str:
    """A token that works now: Strava's last six hours, then a refresh keeps the grant going."""
    if connection.expires_at > timezone.now() + timedelta(minutes=1):
        return connection.access_token
    data = _token(refresh_token=connection.refresh_token, grant_type="refresh_token")
    connection.access_token = data["access_token"]
    connection.refresh_token = data["refresh_token"]
    connection.expires_at = _when(data["expires_at"])
    connection.save(update_fields=["access_token", "refresh_token", "expires_at"])
    return connection.access_token


def disconnect(connection: StravaConnection) -> None:
    """Revoke the grant at Strava when it still answers, and forget the tokens either way."""
    try:
        requests.post(DEAUTHORIZE_URL, data={"access_token": _access_token(connection)}, timeout=_TIMEOUT)
    except (StravaError, requests.RequestException):
        pass
    connection.delete()


def tcx(ride: VirtualRide, points: list) -> bytes:
    """The ride as a gzipped TCX file: a lap of trackpoints with position, height, power, cadence, pulse."""
    start = ride.finished_at - timedelta(seconds=ride.duration_s)

    def stamp(moment: datetime) -> str:
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def sub(parent, tag, text=None, **attrs):
        element = ET.SubElement(parent, f"{{{_TCX}}}{tag}", attrs)
        if text is not None:
            element.text = str(text)
        return element

    root = ET.Element(f"{{{_TCX}}}TrainingCenterDatabase")
    activity = sub(sub(root, "Activities"), "Activity", Sport="Biking")
    sub(activity, "Id", stamp(start))
    lap = sub(activity, "Lap", StartTime=stamp(start))
    sub(lap, "TotalTimeSeconds", round(ride.duration_s, 1))
    sub(lap, "DistanceMeters", round(ride.distance_m, 1))
    sub(lap, "MaximumSpeed", round(ride.max_speed_kmh / 3.6, 2))
    # a kilojoule of work on the pedals is about a kilocalorie burnt
    sub(lap, "Calories", min(65535, round(sum(p[6] for p in points) / 1000)))
    sub(lap, "Intensity", "Active")
    sub(lap, "TriggerMethod", "Manual")
    track = sub(lap, "Track")
    for t, lat, lon, ele, distance, speed, power, cadence, pulse in points:
        point = sub(track, "Trackpoint")
        sub(point, "Time", stamp(start + timedelta(seconds=t)))
        position = sub(point, "Position")
        sub(position, "LatitudeDegrees", f"{lat:.6f}")
        sub(position, "LongitudeDegrees", f"{lon:.6f}")
        sub(point, "AltitudeMeters", round(ele, 1))
        sub(point, "DistanceMeters", round(distance, 1))
        if pulse:
            sub(sub(point, "HeartRateBpm"), "Value", int(pulse))
        if cadence:
            sub(point, "Cadence", min(254, int(cadence)))
        extension = ET.SubElement(sub(point, "Extensions"), f"{{{_TPX}}}TPX")
        ET.SubElement(extension, f"{{{_TPX}}}Speed").text = str(round(speed, 2))
        ET.SubElement(extension, f"{{{_TPX}}}Watts").text = str(int(power))
    return gzip.compress(ET.tostring(root, xml_declaration=True, encoding="UTF-8"))


def _fail(record: StravaUpload, message: str) -> StravaUpload:
    record.status, record.error = StravaUpload.Status.FAILED, strip_tags(message)[:300]
    record.save()
    return record


def _apply(record: StravaUpload, body: dict) -> StravaUpload:
    """Strava's answer about an upload: still processing, an activity, or why there is none."""
    record.upload_id = str(body.get("id_str") or body.get("id") or record.upload_id)
    if body.get("error"):
        return _fail(record, str(body["error"]))
    if body.get("activity_id"):
        record.status, record.activity_id, record.error = StravaUpload.Status.DONE, str(body["activity_id"]), ""
    else:
        record.status = StravaUpload.Status.PROCESSING
    record.save()
    return record


def _call(connection: StravaConnection, method: str, url: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(
            method, url, headers={"Authorization": f"Bearer {_access_token(connection)}"}, timeout=_TIMEOUT, **kwargs
        )
    except requests.RequestException as exc:
        raise StravaError(type(exc).__name__) from None
    if response.status_code == 401:
        raise StravaError("Strava no longer accepts this connection", revoked=True)
    return response


def upload(ride: VirtualRide) -> StravaUpload:
    """Send one ride to the member's Strava as a Virtual Ride. A failure is recorded, not raised."""
    record, _created = StravaUpload.objects.update_or_create(
        ride=ride,
        defaults={"status": StravaUpload.Status.PROCESSING, "upload_id": "", "activity_id": "", "error": ""},
    )
    connection = StravaConnection.objects.filter(user_id=ride.user_id).first()
    track = RideTrack.objects.filter(ride=ride).first()
    if connection is None or track is None:
        return _fail(record, "Not connected to Strava" if connection is None else "The ride has no track")
    data = {
        "data_type": "tcx.gz",
        # the type Strava would guess from a TCX is a plain ride; this is a ride on a trainer in a virtual world
        "sport_type": "VirtualRide",
        "name": ride.route_name or ride.route,
        "external_id": f"universalbicycle-virtual-ride-{ride.pk}",
    }
    files = {"file": (f"virtual-ride-{ride.pk}.tcx.gz", tcx(ride, track.points), "application/gzip")}
    try:
        response = _call(connection, "POST", UPLOADS_URL, data=data, files=files)
    except StravaError as exc:
        if exc.revoked:
            connection.delete()
        return _fail(record, str(exc))
    if response.status_code != 201:
        return _fail(record, response.text or f"Strava answered {response.status_code}")
    return _apply(record, response.json())


def refresh(record: StravaUpload) -> StravaUpload:
    """Ask Strava how a processing upload is going; anything else is already settled."""
    connection = StravaConnection.objects.filter(user_id=record.ride.user_id).first()
    if record.status != StravaUpload.Status.PROCESSING or not record.upload_id or connection is None:
        return record
    try:
        response = _call(connection, "GET", f"{UPLOADS_URL}/{record.upload_id}")
    except StravaError as exc:
        if exc.revoked:
            connection.delete()
            return _fail(record, str(exc))
        return record  # Strava unreachable for now: ask again later
    if response.status_code != 200:
        return record
    return _apply(record, response.json())
