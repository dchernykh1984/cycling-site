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
# is listed BEFORE the track -- so matching wpt would take a POI hundreds of km from the start. A
# namespace prefix (<gpx:trkpt>) is allowed, and lat/lon are read separately because XML attribute
# order is not significant.
_GPX_TRKPT = re.compile(r"<(?:\w+:)?(?:trkpt|rtept)\b([^>]*)>", re.IGNORECASE)
_ATTR_LAT = re.compile(r"\blat=\"(-?\d+(?:\.\d+)?)\"", re.IGNORECASE)
_ATTR_LON = re.compile(r"\blon=\"(-?\d+(?:\.\d+)?)\"", re.IGNORECASE)
# A Google/Strava <gx:Track> stores the path as space-separated "lon lat [alt]" in <gx:coord>.
_GX_COORD = re.compile(r"<gx:coord>\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE)
# The <coordinates> body of every LineString. A KML often carries standalone <Point> placemarks (an
# overview pin, the finish, controls) and decorative or bounding-box lines besides the route, so we
# take not the first line but the longest -- the route has far more points than any decoration.
_KML_LINE_COORDS = re.compile(r"<LineString\b.*?<coordinates>\s*(.*?)\s*</coordinates>", re.IGNORECASE | re.DOTALL)
_KML_FIRST_LNG_LAT = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")
# A commented-out or CDATA-wrapped <trkpt>/<coordinates> is not real markup: it is text a decoy could
# place above the true track to steal the start. Drop both before scanning so only live points count.
_XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_XML_CDATA = re.compile(r"<!\[CDATA\[.*?\]\]>", re.DOTALL)


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
    track = _XML_CDATA.sub(" ", _XML_COMMENT.sub(" ", track))
    point = _gpx_start(track) or _kml_start(track)
    if point is None:
        return None
    lat, lng = point
    if -90 <= lat <= 90 and -180 <= lng <= 180 and (lat, lng) != (0.0, 0.0):
        return lat, lng
    return None


def _gpx_start(track: str) -> tuple[float, float] | None:
    """The first (lat, lng) of a GPX track/route point, reading lat and lon in either order."""
    for match in _GPX_TRKPT.finditer(track):
        attrs = match.group(1)
        lat, lon = _ATTR_LAT.search(attrs), _ATTR_LON.search(attrs)
        if lat and lon:
            return float(lat.group(1)), float(lon.group(1))
    return None


def _kml_start(track: str) -> tuple[float, float] | None:
    """The first (lat, lng) of the longest LineString in a KML file, or None.

    The longest coordinate list is the route; shorter ones are decorations, bounding boxes or
    finish/overview markers that must not be mistaken for the start. KML orders each pair lon,lat.
    """
    longest, most = None, -1
    for body in _KML_LINE_COORDS.findall(track):
        points = body.split()
        if len(points) > most:
            most, longest = len(points), body
    if longest is not None:
        first = _KML_FIRST_LNG_LAT.search(longest)
        if first is not None:
            return float(first.group(2)), float(first.group(1))  # stored lon,lat -> return lat,lng
    # A <gx:Track> (Google/Strava GPS export) has no LineString; its first <gx:coord> is the start.
    coord = _GX_COORD.search(track)
    if coord is not None:
        return float(coord.group(2)), float(coord.group(1))  # "lon lat" -> lat,lng
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
