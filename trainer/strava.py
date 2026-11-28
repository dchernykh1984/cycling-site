"""Sending a member's virtual rides to Strava as Virtual Ride activities.

Signing in with Strava asks for ``read`` only and keeps no token (``specs/site/accounts.md``,
FR-ACC-007). Uploading needs ``activity:write``: the member grants it separately from the profile, its
tokens live sealed in ``StravaConnection`` (``trainer.secret_box``) and are refreshed here when they
expire. Every call goes through ``requests``, which the tests patch -- they never reach Strava.
"""

import gzip
import re
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import cast
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests
from allauth.socialaccount.providers.strava.provider import StravaProvider
from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.debug import sensitive_variables

from . import fit, secret_box
from .invitation import invitation
from .models import RideTrack, StravaConnection, StravaUpload, VirtualRide

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"  # noqa: S105 -- an address, not a secret
DEAUTHORIZE_URL = "https://www.strava.com/oauth/deauthorize"
UPLOADS_URL = "https://www.strava.com/api/v3/uploads"
STARRED_URL = "https://www.strava.com/api/v3/segments/starred"
SEGMENT_STREAMS_URL = "https://www.strava.com/api/v3/segments/{}/streams"
EFFORTS_URL = "https://www.strava.com/api/v3/segment_efforts"
EFFORT_STREAMS_URL = "https://www.strava.com/api/v3/segment_efforts/{}/streams"
# "read" keeps the athlete's name in the token answer; "activity:write" is what uploading needs
SCOPE = "read,activity:write"
# what the live segments add: the member's own efforts on a segment and their streams (Strava's reference asks
# "read_all" for an effort's streams); the starred list and a segment's own line need "read" alone
SEGMENTS_SCOPE = "activity:read_all"
# a segment's line and the best effort's times come thinned to this many points: a phone's page draws and reads them
SEGMENT_POINTS = 400
STARRED_PAGE = 200  # Strava's most a page: one request lists a member's starred segments
EFFORTS_PAGE = 200
# Saving a ride waits for Strava (a token refresh, then the upload) on one of the site's four request
# threads: a slow Strava fails the upload, which can be sent again, rather than hold the thread
_TIMEOUT = 10
_TCX = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_TPX = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
# Strava names the activity a duplicate upload matches; that activity is this ride, sent before
_DUPLICATE_OF = re.compile(r"duplicate of.*?activit(?:y|ies)\D{0,3}(\d+)", re.IGNORECASE | re.DOTALL)
ET.register_namespace("", _TCX)
ET.register_namespace("tpx", _TPX)


class StravaError(Exception):
    """Strava refused or could not be reached; ``revoked`` when the member's grant no longer works."""

    def __init__(self, message: str, revoked: bool = False):
        super().__init__(message)
        self.revoked = revoked


def _app() -> dict:
    return cast(dict, settings.SOCIALACCOUNT_PROVIDERS[StravaProvider.id]["APP"])


def configured() -> bool:
    """The site has a Strava application to upload with."""
    app = _app()
    return bool(app.get("client_id") and app.get("secret"))


def available() -> bool:
    """The site has a Strava application to upload with and can keep a member's tokens sealed."""
    return configured() and secret_box.available()


def reads_segments(connection: StravaConnection | None) -> bool:
    """The member allowed the live segments: their starred segments and their own efforts on them."""
    return connection is not None and SEGMENTS_SCOPE in connection.scope.split(",")


def authorize_url(redirect_uri: str, state: str, segments: bool = False) -> str:
    query = {
        "client_id": _app()["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": f"{SCOPE},{SEGMENTS_SCOPE}" if segments else SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _when(epoch) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=UTC)


# the app's secret, a code or a token and Strava's answer: none of this frame's or deeper ones' in an error report
@sensitive_variables()
def _token(**data) -> dict:
    app = _app()
    try:
        response = requests.post(
            TOKEN_URL, data={"client_id": app["client_id"], "client_secret": app["secret"], **data}, timeout=_TIMEOUT
        )
    except requests.RequestException as exc:
        raise StravaError(type(exc).__name__) from None
    if response.status_code != HTTPStatus.OK:
        # a code or refresh token Strava no longer accepts: the member revoked the grant or never gave it
        raise StravaError(
            f"Strava answered {response.status_code}",
            revoked=response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED),
        )
    return response.json()


@sensitive_variables("code", "data")
def connect(user, code: str, scope: str = SCOPE) -> StravaConnection:
    """Trade the code Strava sent back for tokens and keep them for this member, with what Strava said they allowed."""
    data = _token(code=code, grant_type="authorization_code")
    athlete = data.get("athlete") or {}
    name = " ".join(part for part in (athlete.get("firstname"), athlete.get("lastname")) if part)
    connection, _created = StravaConnection.objects.update_or_create(
        user=user,
        defaults={
            "athlete_id": athlete.get("id") or 0,
            "athlete_name": name[:120],
            "access_token": secret_box.seal(data["access_token"]),
            "refresh_token": secret_box.seal(data["refresh_token"]),
            "expires_at": _when(data["expires_at"]),
            "scope": scope[:200],
        },
    )
    return connection


@sensitive_variables("access", "refresh", "data")
def _access_token(connection: StravaConnection) -> str:
    """A token that works now: Strava's last six hours, then a refresh keeps the grant going."""
    access, refresh = secret_box.open_sealed(connection.access_token), secret_box.open_sealed(connection.refresh_token)
    if access is None or refresh is None:
        # the site's key was changed or lost: nothing can be sent with this grant, so the member connects again
        raise StravaError("The site can no longer read this connection", revoked=True)
    if connection.expires_at > timezone.now() + timedelta(minutes=1):
        return access
    data = _token(refresh_token=refresh, grant_type="refresh_token")
    connection.access_token = secret_box.seal(data["access_token"])
    connection.refresh_token = secret_box.seal(data["refresh_token"])
    connection.expires_at = _when(data["expires_at"])
    connection.save(update_fields=["access_token", "refresh_token", "expires_at"])
    return data["access_token"]


def disconnect(connection: StravaConnection) -> None:
    """Forget the member's grant; ``revoke_at_strava`` takes it back at Strava on the way out."""
    connection.delete()


@receiver(pre_delete, sender=StravaConnection)
@sensitive_variables()  # the token travels down through the HTTP library
def revoke_at_strava(sender, instance: StravaConnection, **kwargs) -> None:
    """Whatever removes a grant -- the member turning it off, their account deleted -- revokes it at Strava too.

    Best effort: Strava may not answer, and the tokens go either way. A grant Strava already refused
    (``revoked``) is not asked about again.
    """
    if instance.revoked:
        return
    try:
        requests.post(DEAUTHORIZE_URL, data={"access_token": _access_token(instance)}, timeout=_TIMEOUT)
    except (StravaError, requests.RequestException):
        pass


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


def ride_file(ride: VirtualRide, track: RideTrack, gzipped: bool = True) -> tuple[str, bytes, str]:
    """The ride's file for an upload: a FIT when it carries the rider's RR intervals, which a TCX has no place for,
    else the TCX, gzipped for Strava; as (name, bytes, type)."""
    if track.rr:
        return f"virtual-ride-{ride.pk}.fit", fit.activity(ride, track.points, track.rr), "application/octet-stream"
    if gzipped:
        return f"virtual-ride-{ride.pk}.tcx.gz", tcx(ride, track.points), "application/gzip"
    return f"virtual-ride-{ride.pk}.tcx", gzip.decompress(tcx(ride, track.points)), "application/xml"


def _fail(record: StravaUpload, message: str) -> StravaUpload:
    record.status, record.error = StravaUpload.Status.FAILED, strip_tags(message)[:300]
    record.save()
    return record


def _apply(record: StravaUpload, body: dict) -> StravaUpload:
    """Strava's answer about an upload: still processing, an activity, or why there is none."""
    record.upload_id = str(body.get("id_str") or body.get("id") or record.upload_id)
    error = str(body.get("error") or "")
    earlier = _DUPLICATE_OF.search(error)
    if earlier:
        # an earlier try reached Strava though its answer did not reach us: the ride is there
        record.status, record.activity_id, record.error = StravaUpload.Status.DONE, earlier.group(1), ""
        record.save()
        return record
    if error:
        return _fail(record, error)
    if body.get("activity_id"):
        record.status, record.activity_id, record.error = StravaUpload.Status.DONE, str(body["activity_id"]), ""
    else:
        record.status = StravaUpload.Status.PROCESSING
    record.save()
    return record


@sensitive_variables()  # the token travels down through the HTTP library as its Authorization header
def _call(connection: StravaConnection, method: str, url: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(
            method, url, headers={"Authorization": f"Bearer {_access_token(connection)}"}, timeout=_TIMEOUT, **kwargs
        )
    except requests.RequestException as exc:
        raise StravaError(type(exc).__name__) from None
    if response.status_code == HTTPStatus.UNAUTHORIZED:
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
        "data_type": "fit" if track.rr else "tcx.gz",
        # the type Strava would guess from a TCX is a plain ride; this is a ride on a trainer in a virtual world
        "sport_type": "VirtualRide",
        "name": ride.route_name or ride.route,
        "description": invitation(ride.user),
        "external_id": f"universalbicycle-virtual-ride-{ride.pk}",
    }
    files = {"file": ride_file(ride, track)}
    try:
        response = _call(connection, "POST", UPLOADS_URL, data=data, files=files)
    except StravaError as exc:
        if exc.revoked:
            connection.revoked = True
            connection.delete()
        return _fail(record, str(exc))
    if response.status_code != HTTPStatus.CREATED:
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
            connection.revoked = True
            connection.delete()
            return _fail(record, str(exc))
        return record  # Strava unreachable for now: ask again later
    if response.status_code != HTTPStatus.OK:
        return record
    return _apply(record, response.json())


# -- Live segments: the member's starred segments and their own efforts on them, read for their own ride -----------
# Strava's API agreement lets a member's data be shown to that member only: what these read goes to the member's own
# page and is kept nowhere on the site.


def _read(connection: StravaConnection, url: str, **params) -> requests.Response:
    """A read with the member's grant; a grant Strava no longer accepts is forgotten, as an upload forgets it."""
    try:
        return _call(connection, "GET", url, params=params)
    except StravaError as exc:
        if exc.revoked:
            connection.revoked = True
            connection.delete()
        raise


def _json(response: requests.Response):
    if response.status_code != HTTPStatus.OK:
        raise StravaError(f"Strava answered {response.status_code}")
    try:
        return response.json()
    except ValueError:  # a proxy's page in place of Strava's answer
        raise StravaError("Strava answered without JSON") from None


def _streams(response: requests.Response) -> dict:
    """Streams keyed by their type, as ``key_by_type`` asks: any other shape is Strava's trouble, not the site's."""
    body = _json(response)
    if not isinstance(body, dict):
        raise StravaError("Strava gave the streams in another shape")
    return body


def _thin(rows: list, most: int = SEGMENT_POINTS) -> list:
    """At most ``most`` of the rows, evenly, the last one kept: where the line or the times end."""
    if len(rows) <= most:
        return rows
    step = (len(rows) - 1) / (most - 1)
    return [rows[round(i * step)] for i in range(most)]


def _pair(value) -> list[float] | None:
    return [float(value[0]), float(value[1])] if isinstance(value, list) and len(value) == 2 else None


def starred_segments(connection: StravaConnection) -> list[dict]:
    """The member's starred segments to ride (Strava's "Ride" ones), with their best time where Strava gives it."""
    out = []
    for seg in _json(_read(connection, STARRED_URL, per_page=STARRED_PAGE)) or []:
        start, end = _pair(seg.get("start_latlng")), _pair(seg.get("end_latlng"))
        if seg.get("activity_type") != "Ride" or start is None or end is None:
            continue
        pr = (seg.get("athlete_pr_effort") or {}).get("pr_elapsed_time")
        out.append(
            {
                "id": int(seg["id"]),
                "name": str(seg.get("name") or "")[:200],
                "distance_m": float(seg.get("distance") or 0),
                "average_grade": float(seg.get("average_grade") or 0),
                "start": start,
                "end": end,
                "pr_s": float(pr) if pr else None,
            }
        )
    return out


def _efforts(connection: StravaConnection, segment_id: int) -> list[dict] | None:
    """The member's own efforts on a segment, or None without the Strava subscription that lists them."""
    response = _read(connection, EFFORTS_URL, segment_id=segment_id, per_page=EFFORTS_PAGE)
    if response.status_code in (HTTPStatus.PAYMENT_REQUIRED, HTTPStatus.FORBIDDEN):
        return None
    return [e for e in _json(response) or [] if e.get("elapsed_time")]


def _effort_times(connection: StravaConnection, effort_id: int) -> list[list[float]]:
    """How far into the segment the effort was at each of its seconds: [[metres, seconds], ...] from its start.

    None to be had -- an activity Strava will not give the streams of -- leaves the page the effort's time spread
    evenly along the segment, not the segment without its best time.
    """
    try:
        streams = _streams(
            _read(connection, EFFORT_STREAMS_URL.format(effort_id), keys="distance,time", key_by_type="true")
        )
    except StravaError as exc:
        if exc.revoked:
            raise
        return []
    dist, time = (streams.get("distance") or {}).get("data") or [], (streams.get("time") or {}).get("data") or []
    if not dist or len(dist) != len(time):
        return []
    return _thin([[round(d - dist[0], 1), round(t - time[0], 1)] for d, t in zip(dist, time, strict=True)])


def segment(connection: StravaConnection, segment_id: int) -> dict:
    """One starred segment to ride: its line with heights, the member's own efforts' times and their best one's pace."""
    streams = _streams(
        _read(
            connection,
            SEGMENT_STREAMS_URL.format(segment_id),
            keys="latlng,distance,altitude",
            key_by_type="true",
        )
    )
    ll = (streams.get("latlng") or {}).get("data") or []
    dist = (streams.get("distance") or {}).get("data") or []
    alt = (streams.get("altitude") or {}).get("data") or [0] * len(ll)
    if len(ll) < 2 or len(dist) != len(ll) or len(alt) != len(ll):
        raise StravaError("Strava gave no line for this segment")
    points = _thin(
        [[round(p[0], 6), round(p[1], 6), round(a, 1), round(d, 1)] for p, d, a in zip(ll, dist, alt, strict=True)]
    )
    efforts = _efforts(connection, segment_id)
    best = min(efforts, key=lambda e: e["elapsed_time"]) if efforts else None
    return {
        "id": segment_id,
        "distance_m": float(dist[-1]),
        "points": points,
        # None: Strava lists a member's efforts only with its subscription
        "efforts": None if efforts is None else sorted(float(e["elapsed_time"]) for e in efforts),
        "best": (
            {
                "elapsed_s": float(best["elapsed_time"]),
                "date": str(best.get("start_date_local") or best.get("start_date") or "")[:10],
                "times": _effort_times(connection, int(best["id"])),
            }
            if best
            else None
        ),
    }
