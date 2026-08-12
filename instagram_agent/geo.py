"""Turn an address from a post into a point, and that point into a venue the site already has.

A club writes where it meets ("ul. Al-Farabi 40, the Halyk Bank car park") and nothing else: no
coordinates, and no two clubs write the same place the same way. Left alone, every announcement
added another node -- this site carried one Almaty car park four times over, twice with identical
coordinates -- and an event hung on a node without coordinates shows in the middle of the city.

So the address is geocoded, and the point is used twice: to recognise a venue that is already there,
and, when there is none, to give the new one a real place on the map.

What decides a match is the name; the distance vetoes. Measured on this site's own venues, two
different places sit 43 m apart while two spellings of one place sit 75 m apart, so distance alone
cannot tell them apart. But the site also carries two venues both called "Industrialka" 2.8 km
apart, which the name alone cannot tell apart either. Together they answer both.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

from agent import dedup

# Recognising a venue the site already has is every agent's problem, not this geocoder's, so it
# lives in agent.venues. The names stay reachable here because this module is what the Instagram
# runner and its tests talk to.
from agent.venues import (  # noqa: F401  (re-exported for this agent's runner and tests)
    Point,
    city_point,
    distance_metres,
    existing_venue,
    same_name,
    same_place,
    venue_words,
    venues_of,
)

_NOMINATIM = "https://nominatim.openstreetmap.org/search?{query}"
# Nominatim asks every caller to identify itself and to stay under one request a second. A run can
# read a dozen announcements in a burst, so the second is kept here rather than assumed: being
# turned away by a service for asking too fast is a week this project has already spent once.
_USER_AGENT = "universalbicycle.team events agent (contact via https://universalbicycle.team)"
_TIMEOUT = 20
_SECONDS_BETWEEN_CALLS = 1.0
_asked_at = 0.0


def _query(venue: str, city: str, country: str) -> str:
    address = ", ".join(part for part in (venue, city, country) if part)
    return urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": "1", "addressdetails": "1"})


# What a post wraps around an address that the geocoder cannot see past: "(parkovka Halyk Banka)".
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
# The first word of an address when it merely names the kind of road, with or without its dot.
_FIRST_WORD = re.compile(r"^\s*(\S+?)\.?\s+")
# Road kinds as dedup.title_tokens renders them, so "ul.", "prospekt" and their Cyrillic spellings
# all land here. Only road kinds: stripping a word like "park" would change what is being asked.
_ROAD_KINDS = {"ul", "ulitsa", "pr", "prospekt"}


def _spellings(venue: str) -> list[str]:
    """The venue as written, then cleaned, for asking a geocoder that matches addresses literally.

    Measured against the address that broke: "ul. Al-Farabi, 40 (parkovka Halyk Banka)" finds
    nothing as written; with the parenthetical stripped AND the road kind dropped it resolves to the
    metre, because the service knows better than the post whether Al-Farabi is a street or an
    avenue. The in-between spelling -- parenthetical stripped, road kind kept -- is never asked: it
    is the one that confidently answered with a namesake road 25 km away.
    """
    cleaned = _PARENTHETICAL.sub("", venue).strip()
    first = _FIRST_WORD.match(cleaned)
    if first and dedup.title_tokens(first.group(1)) <= _ROAD_KINDS:
        cleaned = cleaned[first.end() :].strip()
    if cleaned and cleaned != venue:
        return [venue, cleaned]
    return [venue]


def locate(venue: str, city: str, country: str) -> Point | None:
    """The point an address names, or None when the geocoder does not recognise it.

    Ask in the language the place is written in locally. Measured against this service: the Almaty
    addresses these clubs post resolve to the metre in Russian and return nothing at all
    transliterated, so an address must go out as the post wrote it, never romanised on the way.

    Callers must check the answer is where they expect -- a geocoder handed a street it does not
    know can answer with something of that name in another country.
    """
    if not venue:
        return None
    try:
        for spelling in _spellings(venue):
            point = _ask(spelling, city, country)
            if point is not None:
                if spelling != venue:
                    print(f"  ~ {venue!r} was found as {spelling!r}", flush=True)
                return point
    except _UnreachableError:
        return None
    print(f"  ~ the geocoder does not know {venue!r}", flush=True)
    return None


class _UnreachableError(Exception):
    """The service could not be asked at all -- a different failure from an unknown address."""


def _ask(venue: str, city: str, country: str) -> Point | None:
    """One question to the geocoder; None when it has no answer for this spelling."""
    _wait_our_turn()
    request = urllib.request.Request(
        _NOMINATIM.format(query=_query(venue, city, country)), headers={"User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            found = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:
        # "The service refused us" and "nobody knows this address" both leave an event without a
        # point, and they need opposite fixes, so they must not read the same in a log. And a
        # service that refused one spelling will refuse the next: asking again only wastes the
        # seconds the throttle makes each question cost.
        print(f"  ~ the geocoder could not be asked about {venue!r}: {exc}", flush=True)
        raise _UnreachableError from exc
    return _first_point(found)


def _wait_our_turn() -> None:
    """Hold to one request a second, as the service asks."""
    global _asked_at
    since = time.monotonic() - _asked_at
    if since < _SECONDS_BETWEEN_CALLS:
        time.sleep(_SECONDS_BETWEEN_CALLS - since)
    _asked_at = time.monotonic()


def _first_point(found: object) -> Point | None:
    if not isinstance(found, list) or not found:
        return None
    try:
        return float(found[0]["lat"]), float(found[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None
