"""Recognising that a venue an announcement names is one the site already carries.

Every agent that places an event needs this, so it lives here rather than beside one agent's
geocoder. Left out, each announcement adds another node: this site carried one Almaty car park four
times over, and later grew a second "magazin Athletex Pro, Atakent" beside the first because the
model happened to write the first letter in lower case.

What decides a match is the name; the distance vetoes. Measured on this site's own venues, two
different places sit 43 m apart while two spellings of one place sit 75 m apart, so distance alone
cannot tell them apart. But the site also carries two venues both called "Industrialka" 2.8 km
apart, which the name alone cannot tell apart either. Together they answer both. When neither venue
has a point -- the usual case for an event read off a chat message -- the name decides on its own.

Nothing here does I/O: the tree is whatever the caller already fetched.
"""

from __future__ import annotations

import math

from agent import dedup, locations

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


def city_node(tree: list, city_id: int) -> dict | None:
    """The city's own node in the fetched tree, or None when the tree does not carry it."""
    for country in tree or []:
        for region in country.get("children") or []:
            for city in region.get("children") or []:
                if city.get("id") == city_id:
                    return city
    return None


def city_point(tree: list, city_id: int) -> Point | None:
    """Where a city itself sits, for checking a geocoder's answer landed in it."""
    city = city_node(tree, city_id)
    return _point_of(city) if city else None


def venues_of(tree: list, city_id: int) -> list[dict]:
    """The start venues already under a city: ``[{"id", "names", "point"}]``."""
    city = city_node(tree, city_id)
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


def candidate_point(candidate) -> Point | None:
    """A candidate's own coordinates, or None -- most events read off a chat message have none."""
    lat, lng = getattr(candidate, "lat", None), getattr(candidate, "lng", None)
    if lat is None or lng is None:
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def existing_venue(venues: list[dict], name: str, point: Point | None) -> int | None:
    """The id of a venue on the site that is this same place, or None."""
    if not locations.has_real_name(name):
        return None
    for venue in venues:
        if any(same_place(name, point, existing, venue["point"]) for existing in venue["names"]):
            return venue["id"]
    return None
