"""A guest's own region, which the calendar, the list and the map open on (#332).

The site's network provider adds the visitor's approximate coordinates to each request it passes on,
worked out from the IP address on its side; this module makes no lookup of its own, stores neither
the point nor the address, and a header it does not get simply leaves the calendar as it was. The region is the
one the nearest of the site's own cities lies in -- not the region whose centre is nearest: the centre
of a large region can lie further off than a small neighbour's.
"""

from __future__ import annotations

import math

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from agent.venues import distance_metres

#: Set once a guest's region has been put in their filter: a guest who then clears it is not handed
#: it again on the next page of the visit.
OFFERED_COOKIE = "guest_region_offered"

_KM_PER_DEGREE = 111.0


def is_bot(request) -> bool:
    """A crawler or a link preview, by its user agent: it reads the calendar as it is, unfiltered."""
    agent = (request.META.get("HTTP_USER_AGENT") or "").lower()
    return not agent or any(marker in agent for marker in settings.BOT_USER_AGENT_MARKERS)


def visitor_point(request) -> tuple[float, float] | None:
    """The coordinates the network provider reports for the visitor, if it reports any."""
    try:
        lat = float(request.META["HTTP_CF_IPLATITUDE"])
        lng = float(request.META["HTTP_CF_IPLONGITUDE"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def nearest_region(point: tuple[float, float]):
    """The region of the site's public city nearest to ``point``, or None when none lies within
    ``GUEST_REGION_RADIUS_KM``."""
    from locations.models import Location, public_places

    radius_km = settings.GUEST_REGION_RADIUS_KM
    lat, lng = point
    # A box around the point first, so that only a handful of cities are measured exactly.
    # shortcut: a box that crosses the 180th meridian finds nothing beyond it; widen it when the
    # site has cities on both sides of that line.
    dlat = radius_km / _KM_PER_DEGREE
    dlng = radius_km / (_KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    cities = Location.objects.filter(
        public_places(),
        depth=3,
        is_deleted=False,
        lat__range=(lat - dlat, lat + dlat),
        lng__range=(lng - dlng, lng + dlng),
    )
    measured = []
    for city in cities:
        metres = distance_metres(point, (float(city.lat), float(city.lng)))
        if metres is not None and metres <= radius_km * 1000:
            measured.append((metres, city))
    if not measured:
        return None
    return min(measured, key=lambda pair: pair[0])[1].get_parent()


def has_upcoming_events(region, user) -> bool:
    """Whether ``user`` would find any event still to come in ``region``."""
    from calendar_app.models import Competition
    from calendar_app.visibility import listed_for

    today = timezone.localdate()
    events = Competition.objects.filter(
        Q(date_end__gte=today) | Q(date_end__isnull=True, date_start__gte=today),
        status=Competition.Status.APPROVED,
        is_deleted=False,
        location__path__startswith=region.path,
    )
    return listed_for(events, user).exists()


def guest_region(request):
    """The region to open a guest's calendar on, or None to leave the calendar whole.

    Only for a visitor who is not signed in (a member opens on their own preferences), who is not a
    crawler or a link preview, who has not been handed their region earlier in the visit, and whose
    region has something still to come.
    """
    if request.user.is_authenticated or is_bot(request) or request.COOKIES.get(OFFERED_COOKIE):
        return None
    point = visitor_point(request)
    region = nearest_region(point) if point else None
    if region is None or not has_upcoming_events(region, request.user):
        return None
    return region
