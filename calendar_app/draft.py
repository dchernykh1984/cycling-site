"""What another page hands the event form to start from (SubmitDraftView), besides the words, the date, the types and
the disciplines: the venue of a virtual route's start, registration with its categories, a route's track to attach and
the virtual ride or race the event is ridden in -- what the virtual ride's calendar box sends
(specs/site/site-shell.md).

A draft is the asking member's, kept in their session; the form takes its extras only when it was opened from it and
sends back its key, so a draft left over from another time never lands on an event made by hand later.
"""

from __future__ import annotations

import json
import math
import secrets

from django.core.exceptions import ValidationError
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
#: The trainer page's word that its draft brings registration (a race's): the form field `registration` set to it.
REGISTERS = "1"
MAX_CATEGORIES = 10
MAX_LAPS = 1000
MAX_BIB = 99_999
MAX_PARTICIPANTS = 100_000
FIRST_BIRTH_YEAR = 1900
#: A race's registration settings a draft may set, each as the event form cleans it.
REGISTRATION_SETTINGS = (
    "birth_date_mode",
    "max_participants",
    "additional_info_mode",
    "additional_info_label",
    "show_additional_info_in_list",
    "additional_info_required",
)
#: The lines of an event's picture a draft brings, from the top down.
PICTURE_LINES = ("when", "title", "facts")
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


def _whole(value, low: int, high: int) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high else None


def _year(value) -> str | None:
    """A year of birth as the category editor shows it in years: a string, from 1900 to next year."""
    year = _whole(value, FIRST_BIRTH_YEAR, timezone.localdate().year + 1)
    return str(year) if year is not None else None


def registration(post) -> dict:
    """A race's registration settings for the form to start from: on, and what else the draft sets that the form's own
    fields take; a value they refuse is left to the form's default."""
    from calendar_app.forms import RegistrationSettingsForm

    fields, settings = RegistrationSettingsForm().fields, {"registration_enabled": True}
    for name in REGISTRATION_SETTINGS:
        if name in post:
            try:
                settings[name] = fields[name].clean(post.get(name))
            except ValidationError:
                continue
    return settings


def categories(raw: str) -> list[dict]:
    """Registration categories as the form's category editor reads them in years: a name, who they are for, the years
    of birth, the laps, the bibs and how many may enter; a value out of its range is left out, a row not so made too."""
    try:
        rows = json.loads(raw or "[]")
    except (ValueError, RecursionError):  # json says a nesting too deep with the latter
        return []
    out = []
    for row in rows[:MAX_CATEGORIES] if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
            continue
        out.append(
            {
                "name": row["name"].strip()[:_CATEGORY_NAME_CHARS],
                "male": row.get("male") is True,
                "female": row.get("female") is True,
                "birth_from": _year(row.get("birth_from")),
                "birth_to": _year(row.get("birth_to")),
                "laps": _whole(row.get("laps"), 1, MAX_LAPS),
                "bib_from": _whole(row.get("bib_from"), 1, MAX_BIB),
                "bib_to": _whole(row.get("bib_to"), 1, MAX_BIB),
                "max_participants": _whole(row.get("max_participants"), 1, MAX_PARTICIPANTS),
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


def picture(post) -> dict | None:
    """The picture a chat shows for the event (calendar_app.ride_picture): its route's view with the day and time, the
    title and the route's length and climb over it, as the page wrote them in its language; none for a route without
    a view."""
    from calendar_app import ride_picture

    route = post.get("picture_route", "")
    if ride_picture.view_of(route) is None:
        return None
    lines = {name: " ".join(post.get(f"picture_{name}", "").split())[: ride_picture.MAX_LINE] for name in PICTURE_LINES}
    return {"route": route, **lines}


def ride_of(user, raw: str) -> int | None:
    """The asking member's own ride or race, to come and held by no event, that the event is to be ridden in."""
    from trainer.models import GroupRide

    if not str(raw or "").isdecimal():
        return None
    race = GroupRide.objects.filter(
        pk=int(raw),
        host=user,
        competition__isnull=True,
        cancelled=False,
        start_at__gt=timezone.now(),
    ).first()
    return race.pk if race else None
