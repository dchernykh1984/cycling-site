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
import math
import re
import time
import urllib.parse
import urllib.request

from agent import dedup, locations

_NOMINATIM = "https://nominatim.openstreetmap.org/search?{query}"
# Nominatim asks every caller to identify itself and to stay under one request a second. A run can
# read a dozen announcements in a burst, so the second is kept here rather than assumed: being
# turned away by a service for asking too fast is a week this project has already spent once.
_USER_AGENT = "universalbicycle.team events agent (contact via https://universalbicycle.team)"
_TIMEOUT = 20
_SECONDS_BETWEEN_CALLS = 1.0
_asked_at = 0.0

# Two venues further apart than this are different places whatever they are called. "Industrialka"
# is a district some 5 km across and clubs name the exact corner they start from, so the site
# rightly carries two of them 2.8 km apart -- one name, two start lines.
_TOO_FAR_METRES = 500
# Within this, a single distinctive word in common is enough: "Compass" and "Magazin Compass" are
# one shop, and they sit at the same coordinates.
_CLOSE_METRES = 250

# Two words of a name have to agree before it counts as the same place, and they have to be most of
# the shorter name. Measured against this site's venues: at this setting every pair it calls one
# place is one, and no two distinct venues are merged.
_NAME_OVERLAP = 0.8
_MIN_SHARED_WORDS = 2
_MIN_PREFIX = 4  # "Banka" and "Bank" are one word; "im." and "imeni" are not

Point = tuple[float, float]


def venue_words(name: str) -> set[str]:
    """The words of a venue name, transliterated, with "kh" folded onto "h".

    A borrowed name transliterates apart from its original otherwise: the Cyrillic spelling becomes
    khalyk where the Latin spelling on the same sign reads halyk.
    """
    return {word[1:] if word.startswith("kh") else word for word in dedup.title_tokens(name)}


def _means_the_same(word: str, others: set[str]) -> bool:
    if word in others:
        return True
    return any(
        len(word) >= _MIN_PREFIX and len(other) >= _MIN_PREFIX and (word.startswith(other) or other.startswith(word))
        for other in others
    )


def same_name(name: str, other: str) -> bool:
    """Whether two venue names are two ways of writing one place."""
    words, other_words = venue_words(name), venue_words(other)
    if len(words) < _MIN_SHARED_WORDS or len(other_words) < _MIN_SHARED_WORDS:
        return False
    shared = max(
        sum(1 for word in words if _means_the_same(word, other_words)),
        sum(1 for word in other_words if _means_the_same(word, words)),
    )
    return shared >= _MIN_SHARED_WORDS and shared / min(len(words), len(other_words)) >= _NAME_OVERLAP


def distance_metres(a: Point | None, b: Point | None) -> float | None:
    """Great-circle distance, or None when either point is unknown."""
    if a is None or b is None:
        return None
    lat1, lng1, lat2, lng2 = (math.radians(value) for value in (*a, *b))
    haversine = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(haversine))


def _shares_a_distinctive_word(name: str, other: str) -> bool:
    words, other_words = venue_words(name), venue_words(other)
    return bool({word for word in words & other_words if len(word) >= 4})


def same_place(name: str, point: Point | None, other_name: str, other_point: Point | None) -> bool:
    """Whether two venues are one place: the names decide, the distance vetoes."""
    apart = distance_metres(point, other_point)
    if apart is not None and apart > _TOO_FAR_METRES:
        return False
    if same_name(name, other_name):
        return True
    # A name of one word says too little on its own, but next door it is enough.
    return apart is not None and apart <= _CLOSE_METRES and _shares_a_distinctive_word(name, other_name)


def _city_node(tree: list, city_id: int) -> dict | None:
    for country in tree or []:
        for region in country.get("children") or []:
            for city in region.get("children") or []:
                if city.get("id") == city_id:
                    return city
    return None


def city_point(tree: list, city_id: int) -> Point | None:
    """Where a city itself sits, for checking a geocoder's answer landed in it."""
    city = _city_node(tree, city_id)
    return _point_of(city) if city else None


def venues_of(tree: list, city_id: int) -> list[dict]:
    """The start venues already under a city: ``[{"id", "names", "point"}]``."""
    city = _city_node(tree, city_id)
    if city is None:
        return []
    return [
        {"id": venue["id"], "names": _names_of(venue), "point": _point_of(venue)}
        for venue in city.get("children") or []
        if venue.get("id") is not None
    ]


def _names_of(node: dict) -> list[str]:
    name = node.get("name")
    if isinstance(name, dict):
        return [str(value) for value in name.values() if value]
    return [str(name)] if name else []


def _point_of(node: dict) -> Point | None:
    try:
        return float(node["lat"]), float(node["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def existing_venue(venues: list[dict], name: str, point: Point | None) -> int | None:
    """The id of a venue on the site that is this same place, or None."""
    if not locations.has_real_name(name):
        return None
    for venue in venues:
        if any(same_place(name, point, existing, venue["point"]) for existing in venue["names"]):
            return venue["id"]
    return None


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
