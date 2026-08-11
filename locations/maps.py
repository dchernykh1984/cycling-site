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
from typing import TYPE_CHECKING
from urllib.parse import quote

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:  # pragma: no cover - import kept out of runtime to avoid a models cycle
    from locations.models import Location

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


def start_point(location: Location | None) -> tuple[Decimal, Decimal] | None:
    """The coordinates worth handing to a navigator, or None when there is no such point.

    A country, region or city is not a start line -- somebody who only needs the city types the
    city into their navigator anyway. A city's hidden catch-all venue ("other location") is not one
    either: it exists precisely to say "the announcement did not tell us where", and it may carry
    the city's coordinates so the site can still draw a marker.

    Attributes are read outright rather than through getattr defaults on purpose. Every default here
    would have to be the permissive one (depth 0, not hidden), so a malformed object would quietly
    earn a link -- failing open on the single rule this module exists to enforce. Nothing but a
    Location or None ever reaches this function, and if something else does it should say so.
    """
    if location is None:
        return None
    if location.depth < _VENUE_DEPTH:
        return None
    if location.is_hidden or location.is_system_fallback:
        return None
    if location.lat is None or location.lng is None:
        return None
    return location.lat, location.lng


def _coord(value: Decimal) -> str:
    """A plain decimal string: never scientific notation, never a stray trailing format."""
    return f"{Decimal(value):.6f}"


def map_links(location: Location | None, name: str = "") -> list[MapLink]:
    """Every "open in ..." link for this location, in the order they should be offered.

    Empty when the location has no start point of its own -- callers can simply check the list.
    """
    point = start_point(location)
    if point is None:
        return []
    lat, lng = _coord(point[0]), _coord(point[1])
    # Apple prints q= as the pin's caption. An empty one is not harmless -- it is a caption saying
    # nothing over a pin, so the parameter is left out rather than sent blank.
    caption = f"&q={quote(name.strip(), safe='')}" if name and name.strip() else ""
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
        MapLink("apple", str(_("Apple Maps")), f"https://maps.apple.com/?ll={lat},{lng}{caption}"),
        MapLink(
            "osm",
            str(_("OpenStreetMap")),
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map={_ZOOM}/{lat}/{lng}",
        ),
    ]
