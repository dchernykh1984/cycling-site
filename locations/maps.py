"""Links that open an event's start point in whichever map service the reader already uses.

The point of the feature is a *start line* someone can send to a friend or hand to a navigator.
That is why the rule is deliberately strict: only a real venue's own coordinates qualify. The site's
own map pin may climb the tree to a city or a region when a venue has no point of its own -- useful
for drawing a marker, useless here. A link that quietly resolves to the middle of Aktau is worse
than no link: it is forwarded without checking, and someone drives to a car park where nobody is.

Nothing here talks to the services. Every URL is built by string concatenation from the two
numbers, so the page costs no network call and works with any point, anywhere.

The coordinate order is NOT the same across services -- 2GIS and Yandex take longitude first,
Google, Apple and OpenStreetMap take latitude first. Getting it backwards produces a URL that looks
perfectly normal and points into another hemisphere, so the order is pinned by tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

from django.utils.translation import gettext_lazy as _

# Zoom close enough to show the actual corner of a car park, on the services that take one.
_ZOOM = 17
# The tree is country / region / city / venue; only the deepest level can be a start line.
_VENUE_DEPTH = 4


@dataclass(frozen=True)
class MapLink:
    """One "open in ..." link: what to call it, and where it goes."""

    key: str
    label: str
    url: str


def start_point(location) -> tuple[Decimal, Decimal] | None:
    """The coordinates worth handing to a navigator, or None when there is no such point.

    A country, region or city is not a start line -- somebody who only needs the city types the
    city into their navigator anyway. A city's hidden catch-all venue ("other location") is not one
    either: it exists precisely to say "the announcement did not tell us where", and it may carry
    the city's coordinates so the site can still draw a marker.
    """
    if location is None:
        return None
    if getattr(location, "depth", 0) < _VENUE_DEPTH:
        return None
    if getattr(location, "is_hidden", False) or _is_catch_all(location):
        return None
    lat, lng = getattr(location, "lat", None), getattr(location, "lng", None)
    if lat is None or lng is None:
        return None
    return lat, lng


def _is_catch_all(location) -> bool:
    """Whether this node is a city's system catch-all rather than a real place."""
    try:
        return bool(location.is_system_fallback)
    except Exception:  # a detached or partial object simply is not a catch-all
        return False


def _coord(value: Decimal) -> str:
    """A plain decimal string: never scientific notation, never a stray trailing format."""
    return f"{Decimal(value):.6f}"


def map_links(location, name: str = "") -> list[MapLink]:
    """Every "open in ..." link for this location, in the order they should be offered.

    Empty when the location has no start point of its own -- callers can simply check the list.
    """
    point = start_point(location)
    if point is None:
        return []
    lat, lng = _coord(point[0]), _coord(point[1])
    label = quote(name or "", safe="")
    return [
        MapLink("2gis", str(_("2GIS")), f"https://2gis.com/geo/{lng},{lat}"),
        # ll centres the map; without it Yandex opens wherever it thinks the reader is and the
        # pt marker can sit off-screen entirely, which is the whole failure this feature avoids.
        MapLink(
            "yandex",
            str(_("Yandex Maps")),
            f"https://yandex.ru/maps/?ll={lng},{lat}&z={_ZOOM}&pt={lng},{lat}&l=map",
        ),
        MapLink("google", str(_("Google Maps")), f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"),
        MapLink("apple", str(_("Apple Maps")), f"https://maps.apple.com/?ll={lat},{lng}&q={label}"),
        MapLink(
            "osm",
            str(_("OpenStreetMap")),
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map={_ZOOM}/{lat}/{lng}",
        ),
    ]
