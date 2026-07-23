"""Pull an event's start coordinate out of the GPS track its page links to.

Announcement pages rarely print latitude/longitude, but most carry a route: a .gpx or .kml file, a
route.eduha.info track-editor link that loads one, or a RideWithGPS route that exports as .gpx. The
first point of that track is the start line, which is exactly the venue coordinate we want. The
parsing is pure and unit-tested; the one network call is injected so it can be exercised without I/O.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from collections.abc import Callable

# A direct track file, or a link that resolves to one.
_TRACK_FILE = re.compile(r"https?://[^\s\"'<>]+\.(?:gpx|kml)(?:\?[^\s\"'<>]*)?", re.IGNORECASE)
_EDUHA_LOAD = re.compile(r"route\.eduha\.info/[^\s\"'<>]*[?&]load=([^\s\"'<>&]+)", re.IGNORECASE)
_RWGPS_ROUTE = re.compile(r"https?://(?:www\.)?ridewithgps\.com/routes/(\d+)", re.IGNORECASE)

# Start of the route line, not a point of interest. A GPX track point (trkpt) or route point (rtept)
# is the recorded/planned line; a waypoint (wpt) is a control/finish/POI and, per the GPX schema,
# is listed BEFORE the track -- so matching wpt would take a POI hundreds of km from the start.
_GPX_TRKPT = re.compile(
    r"<(?:trkpt|rtept)\b[^>]*\blat=\"(-?\d+(?:\.\d+)?)\"[^>]*\blon=\"(-?\d+(?:\.\d+)?)\"",
    re.IGNORECASE,
)
# The first coordinate of the route line. A KML file often carries standalone <Point> placemarks
# (an overview pin, the finish, controls) before the <LineString> route, so taking the first
# <coordinates> anywhere would grab a POI; anchor on the LineString's coordinates instead.
_KML_LINE = re.compile(
    r"<LineString\b.*?<coordinates>\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)


def track_url(links: list[str]) -> str | None:
    """The URL of a downloadable GPS track among ``links``, or None.

    A direct .gpx/.kml wins; otherwise a route.eduha link is unwrapped to the file it loads, and a
    RideWithGPS route is turned into its .gpx export. The first match in page order is used, so the
    track the page presents first (usually the main route) is the one we read.
    """
    for link in links:
        # Wrappers first: a route.eduha link ends in ".kml" inside its encoded load= param, so the
        # direct-file test would greedily match the wrapper instead of the file it loads.
        loaded = _EDUHA_LOAD.search(link)
        if loaded:
            inner = urllib.parse.unquote(loaded.group(1))
            # fullmatch, like the direct-file branch: .match would let "a.gpxJUNK" through and we
            # would fetch that verbatim.
            if _TRACK_FILE.fullmatch(inner):
                return inner
        rwgps = _RWGPS_ROUTE.match(link)
        if rwgps:
            return f"https://ridewithgps.com/routes/{rwgps.group(1)}.gpx"
        if _TRACK_FILE.fullmatch(link):
            return link
    return None


def parse_start(track: str) -> tuple[float, float] | None:
    """The (lat, lng) of the first point in a GPX or KML track, or None when unreadable.

    Coordinates outside the valid range are rejected -- a malformed or truncated file must not put a
    venue in the ocean.
    """
    gpx = _GPX_TRKPT.search(track)
    if gpx:
        lat, lng = float(gpx.group(1)), float(gpx.group(2))
    else:
        kml = _KML_LINE.search(track)
        if not kml:
            return None
        lng, lat = float(kml.group(1)), float(kml.group(2))  # KML order is lon,lat
    if -90 <= lat <= 90 and -180 <= lng <= 180 and (lat, lng) != (0.0, 0.0):
        return lat, lng
    return None


def is_fetchable_track_url(url: str) -> bool:
    """Whether ``url`` is safe to download: http(s) to a host that resolves only to public IPs.

    The track URL comes from a page that may be hostile (an aggregator can link anything), so this
    is the SSRF gate: no file:// or other schemes, and no host that resolves to a loopback, private,
    link-local or otherwise reserved address -- which is how a link would reach a cloud metadata
    endpoint or an internal service.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def start_coordinate(links: list[str], fetch: Callable[[str], str]) -> tuple[float, float] | None:
    """Fetch the track a page links to and return its start point, or None on any failure.

    ``fetch`` takes a URL and returns the track text; every error is swallowed so a missing or broken
    track never interrupts the run -- the venue simply keeps whatever coordinate it already had. The
    URL is refused unless it resolves to a public host (see ``is_fetchable_track_url``).
    """
    url = track_url(links)
    if url is None or not is_fetchable_track_url(url):
        return None
    try:
        return parse_start(fetch(url))
    except Exception:
        return None
