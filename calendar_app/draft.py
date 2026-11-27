"""What another page hands the event form to start from (SubmitDraftView), besides the words, the date, the types and
the disciplines: the venue of a virtual route's start, registration with its categories, a route's track to attach and
a virtual race the event is to hold -- what the virtual ride's calendar box sends (specs/site/site-shell.md).

A draft is the asking member's, kept in their session; the form takes its extras only when it was opened from it and
sends back its key, so a draft left over from another time never lands on an event made by hand later.
"""

from __future__ import annotations

import json
import math
import secrets

from django.utils import timezone, translation
from django.utils.translation import gettext

from accounts import roles
from agent.venues import distance_metres
from calendar_app import tracks
from locations.models import Level, Location, chain_is_approved, on_earth, places_seen_by, public_places

#: A virtual route's start in the virtual world: a venue so named within this many metres of it is that start.
VIRTUAL_VENUE_RADIUS_M = 100
#: The public city such a venue hangs under lies within this many metres of the start.
START_CITY_RADIUS_M = 40_000
_ROUTE_NAME_CHARS = 60
#: A draft's track: a route of a few hundred points, far more than one needs and little enough for a session.
MAX_TRACK_BYTES = 512 * 1024
MAX_CATEGORIES = 10
MAX_LAPS = 1000
_CATEGORY_NAME_CHARS = 100  # RegistrationCategory.name
_TRACK_NAME_CHARS = 60
_METRES_PER_DEGREE = 111_000


def new_key() -> str:
    return secrets.token_urlsafe(16)


def _near(places, point: tuple[float, float], radius_m: float) -> list[Location]:
    """The places with coordinates within radius_m of the point, nearest first."""
    dlat = radius_m / _METRES_PER_DEGREE
    dlng = dlat / max(math.cos(math.radians(point[0])), 0.01)
    box = places.filter(
        lat__range=(point[0] - dlat, point[0] + dlat), lng__range=(point[1] - dlng, point[1] + dlng)
    ).exclude(lat=None)
    measured = [(distance_metres(point, (float(p.lat), float(p.lng))), p.pk, p) for p in box]
    return [p for metres, _pk, p in sorted(measured) if metres is not None and metres <= radius_m]


def _venue_names(route_names: dict[str, str]) -> dict[str, str] | None:
    """A virtual route's start, named in each language so that nobody comes to the place to meet."""
    fallback = (route_names.get("ru") or "").strip()
    if not fallback:
        return None
    names = {}
    for lang in ("ru", "kk", "en"):
        route = ((route_names.get(lang) or "").strip() or fallback)[:_ROUTE_NAME_CHARS]
        with translation.override(lang):
            names[lang] = gettext('Virtual world: start of the route "%(route)s"') % {"route": route}
    return names


def virtual_venue(user, lat: str, lng: str, route_names: dict[str, str]) -> int | None:
    """The venue of a virtual route's start, in the virtual world: the one so named within VIRTUAL_VENUE_RADIUS_M of
    it that the member sees, else one proposed now under the nearest public city -- public for an organizer, awaiting
    review for anyone else, usable at once either way, as the event form proposes a venue. None without a point, a
    route's name or a city near it."""
    try:
        point = (float(lat), float(lng))
    except (TypeError, ValueError):
        return None
    names = _venue_names(route_names)
    if not on_earth(*point) or names is None:
        return None
    venues = Location.objects.filter(places_seen_by(user), depth=Level.VENUE, is_deleted=False, name_ru=names["ru"])
    found = _near(venues, point, VIRTUAL_VENUE_RADIUS_M)
    if found:
        return found[0].pk
    cities = Location.objects.filter(public_places(), depth=Level.CITY, is_deleted=False, is_hidden=False)
    near = _near(cities, point, START_CITY_RADIUS_M)
    if not near:
        return None
    city = near[0]
    venue = Location.propose_venue(
        city,
        names["ru"],
        round(point[0], 6),
        round(point[1], 6),
        name_kk=names["kk"],
        name_en=names["en"],
        submitted_by=user,
        approved=roles.at_least(user, roles.PUBLISH_EVENTS) and chain_is_approved(city),
    )
    return venue.pk


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
