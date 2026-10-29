"""Links that open an event's start point in whichever map service the reader already uses.

The point of the feature is a *start line* someone can send to a friend or hand to a navigator.
That is why the rule is deliberately strict: only a real venue's own coordinates qualify. The site's
own map pin may climb the tree to a city or a region when a venue has no point of its own -- useful
for drawing a marker, useless here. A link that quietly resolves to the middle of Aktau is worse
than no link: it is forwarded without checking, and someone drives to a car park where nobody is.

Nothing here talks to the services. Every URL is filled in from the two numbers, so the page costs
no network call and works with any point, anywhere.

Which services are offered, and in what order, is configuration, not code: the catalogue
``MAP_SERVICES`` says how each one opens a point, and ``MAP_LINK_SERVICES`` which of them a
deployment offers its readers. The coordinate order is NOT the same across services -- 2GIS and
Yandex take longitude first, Google, Apple and OpenStreetMap latitude first. Getting it backwards
produces a URL that looks perfectly normal and points into another hemisphere, so the catalogue's
templates are pinned by tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings
from django.utils.translation import gettext

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
    """Every "open in ..." link for this location, in the order the deployment lists the services.

    Empty when the location has no start point of its own -- callers can simply check the list.
    """
    point = start_point(location)
    if point is None:
        return []
    fields = {"lat": _coord(point[0]), "lng": _coord(point[1]), "zoom": _ZOOM}
    caption = name.strip() if name else ""
    links = []
    for key in offered_services():
        service = settings.MAP_SERVICES.get(key)
        if service is None:
            continue  # a key the catalogue does not know: the system check names it
        url = service["url"].format(**fields)
        # A service that captions its pin gets the place's name -- and no caption at all when there is
        # no name: an empty one is a label saying nothing over the pin.
        if caption and service.get("name"):
            url = _with_param(url, service["name"], caption)
        links.append(MapLink(key, gettext(service["label"]), url))
    return links


def offered_services() -> list[str]:
    """The services the deployment lists, as an environment writes them: "2gis, yandex" names two."""
    return [key.strip() for key in settings.MAP_LINK_SERVICES if key.strip()]


def _with_param(url: str, param: str, value: str) -> str:
    """``url`` with one more query parameter, ahead of any #fragment."""
    base, hash_mark, fragment = url.partition("#")
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}{param}={quote(value, safe='')}{hash_mark}{fragment}"
