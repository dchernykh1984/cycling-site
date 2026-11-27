"""What another page hands the event form to start from (SubmitDraftView), besides the words, the date, the types and
the disciplines: the venue at a point, registration with its categories, a route's track to attach and a virtual race
the event is to hold -- what the virtual ride's "Add event" sends (specs/site/site-shell.md).

A draft is the asking member's, kept in their session; the form takes its extras only when it was opened from it and
sends back its key, so a draft left over from another time never lands on an event made by hand later.
"""

from __future__ import annotations

import json
import math
import secrets

from django.utils import timezone

from agent.venues import distance_metres
from calendar_app import tracks
from locations.models import Level, Location, on_earth, public_places

#: How far from a route's start a venue still is its start: the distance two venues are told apart by.
START_VENUE_RADIUS_M = 300
#: A draft's track: a route of a few hundred points, far more than one needs and little enough for a session.
MAX_TRACK_BYTES = 512 * 1024
MAX_CATEGORIES = 10
MAX_LAPS = 1000
_CATEGORY_NAME_CHARS = 100  # RegistrationCategory.name
_TRACK_NAME_CHARS = 60
_METRES_PER_DEGREE = 111_000


def new_key() -> str:
    return secrets.token_urlsafe(16)


def venue_at(lat: str, lng: str) -> int | None:
    """The public venue nearest the point and within START_VENUE_RADIUS_M of it, else None: a route's start where the
    place tree has it, never a venue made up for it."""
    try:
        point = (float(lat), float(lng))
    except (TypeError, ValueError):
        return None
    if not on_earth(*point):
        return None
    dlat = START_VENUE_RADIUS_M / _METRES_PER_DEGREE
    dlng = dlat / max(math.cos(math.radians(point[0])), 0.01)
    venues = Location.objects.filter(
        public_places(),
        depth=Level.VENUE,
        is_hidden=False,
        is_deleted=False,
        lat__range=(point[0] - dlat, point[0] + dlat),
        lng__range=(point[1] - dlng, point[1] + dlng),
    )
    measured = [(distance_metres(point, (float(v.lat), float(v.lng))), v.pk) for v in venues]
    near = [(metres, pk) for metres, pk in measured if metres is not None and metres <= START_VENUE_RADIUS_M]
    return min(near)[1] if near else None


def categories(raw: str) -> list[dict]:
    """Registration categories as the form's category editor reads them: a name, who they are for and the laps; any
    row not so made is left out."""
    try:
        rows = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for row in rows[:MAX_CATEGORIES] if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
            continue
        laps = row.get("laps")
        out.append(
            {
                "name": row["name"].strip()[:_CATEGORY_NAME_CHARS],
                "male": row.get("male") is True,
                "female": row.get("female") is True,
                "birth_from": None,
                "birth_to": None,
                "laps": laps if isinstance(laps, int) and not isinstance(laps, bool) and 0 < laps <= MAX_LAPS else None,
                "bib_from": None,
                "bib_to": None,
                "max_participants": None,
            }
        )
    return out


def track(name: str, gpx: str) -> dict | None:
    """A route's GPX to attach as the event's track file, when it is one the event's map can draw."""
    data = (gpx or "").encode()
    if not data or len(data) > MAX_TRACK_BYTES or tracks.read(data) is None:
        return None
    stem = "".join(c for c in (name or "") if c.isascii() and (c.isalnum() or c in "-_"))[:_TRACK_NAME_CHARS]
    return {"name": (stem or "route") + ".gpx", "gpx": gpx}


def race_of(user, raw: str) -> int | None:
    """The asking member's own race, to come and held by no event, that the event is to hold."""
    from trainer.models import GroupRide

    if not str(raw or "").isdecimal():
        return None
    race = GroupRide.objects.filter(
        pk=int(raw),
        host=user,
        kind=GroupRide.Kind.RACE,
        competition__isnull=True,
        cancelled=False,
        start_at__gt=timezone.now(),
    ).first()
    return race.pk if race else None
