"""Voice chat in a group race: Cloudflare Realtime's media server carries the sound, the site introduces.

Each rider's page keeps one WebRTC connection to Cloudflare. It publishes the microphone as one track
and receives the other riders' tracks over the same connection, so a chat of twenty costs every page
one upload and nineteen small downloads, and the site no sound at all. Cloudflare's API needs the app
secret, so the pages go through the site, which lets a rider hear only the members of their own race:
other riders' session ids never leave the server. Every call goes through ``requests``, which the tests
patch.
"""

import secrets

import requests
from django.conf import settings

from .models import GroupRide, VoiceSession

API = "https://rtc.live.cloudflare.com/v1/apps/{app}"
# A rider waits for these calls while their page sets up sound: long enough for Cloudflare, short
# enough not to hold one of the site's few request threads
_TIMEOUT = 10


class VoiceError(Exception):
    """Cloudflare refused or could not be reached."""


def available() -> bool:
    return bool(settings.CLOUDFLARE_REALTIME_APP_ID and settings.CLOUDFLARE_REALTIME_APP_SECRET)


def _call(method: str, path: str, body: dict | None = None) -> dict:
    url = API.format(app=settings.CLOUDFLARE_REALTIME_APP_ID) + path
    headers = {"Authorization": f"Bearer {settings.CLOUDFLARE_REALTIME_APP_SECRET}"}
    try:
        response = requests.request(method, url, json=body, headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise VoiceError(type(exc).__name__) from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400 or data.get("errorCode"):
        raise VoiceError(data.get("errorDescription") or f"Cloudflare answered {response.status_code}")
    return data


def publish(group: GroupRide, user, offer: str, mid: str) -> str:
    """Open the rider's session and publish their microphone; the answer goes back to their page."""
    session_id = _call("POST", "/sessions/new")["sessionId"]
    track_name = secrets.token_hex(8)
    data = _call(
        "POST",
        f"/sessions/{session_id}/tracks/new",
        {
            "sessionDescription": {"type": "offer", "sdp": offer},
            "tracks": [{"location": "local", "mid": mid, "trackName": track_name}],
        },
    )
    track = (data.get("tracks") or [{}])[0]
    if track.get("errorCode"):
        raise VoiceError(track.get("errorDescription") or track["errorCode"])
    VoiceSession.objects.update_or_create(
        user=user, defaults={"group": group, "session_id": session_id, "track_name": track_name, "mid": mid}
    )
    return data["sessionDescription"]["sdp"]


def subscribe(mine: VoiceSession, others: list[VoiceSession]) -> dict:
    """Have Cloudflare send these riders' microphones down the rider's connection.

    Returns the offer the page must answer (or None), the tracks by rider, and the riders Cloudflare
    could not find -- one who closed their page a moment ago.
    """
    data = _call(
        "POST",
        f"/sessions/{mine.session_id}/tracks/new",
        {"tracks": [{"location": "remote", "sessionId": o.session_id, "trackName": o.track_name} for o in others]},
    )
    by_track = {(o.session_id, o.track_name): o for o in others}
    tracks, failed = [], []
    for track in data.get("tracks") or []:
        other = by_track.get((track.get("sessionId"), track.get("trackName")))
        if other is None:
            continue
        if track.get("errorCode") or not track.get("mid"):
            failed.append(other.track_name)
        else:
            tracks.append({"key": other.track_name, "user_id": other.user_id, "mid": str(track["mid"])})
    renegotiate = data.get("requiresImmediateRenegotiation") and data.get("sessionDescription")
    return {"offer": data["sessionDescription"]["sdp"] if renegotiate else None, "tracks": tracks, "failed": failed}


def answer(mine: VoiceSession, sdp: str) -> None:
    _call("PUT", f"/sessions/{mine.session_id}/renegotiate", {"sessionDescription": {"type": "answer", "sdp": sdp}})


def leave(mine: VoiceSession) -> None:
    """Stop publishing at Cloudflare when it still answers, and leave the chat either way."""
    try:
        _call("PUT", f"/sessions/{mine.session_id}/tracks/close", {"tracks": [{"mid": mine.mid}], "force": True})
    except VoiceError:
        pass
    mine.delete()
