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
# namespace prefix (<gpx:trkpt>) is allowed. Only the tag NAME is matched here (no ".*>" for the
# attributes): the tag's end is found with str.find so a 20 MB file of unterminated "<trkpt" tags
# cannot drive the regex quadratic. lat/lon are read separately, XML attribute order not being fixed.
_GPX_TRKPT = re.compile(r"<(?:\w+:)?(?:trkpt|rtept)\b", re.IGNORECASE)
_ATTR_LAT = re.compile(r"\blat=\"(-?\d+(?:\.\d+)?)\"", re.IGNORECASE)
_ATTR_LON = re.compile(r"\blon=\"(-?\d+(?:\.\d+)?)\"", re.IGNORECASE)
# A Google/Strava <gx:Track> stores the path as space-separated "lon lat [alt]" in <gx:coord>.
_GX_COORD = re.compile(r"<gx:coord>\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_KML_FIRST_LNG_LAT = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


def _drop_spans(text: str, opener: str, closer: str) -> str:
    """Replace every ``opener``..``closer`` span (and an unterminated trailing opener) with a space.

    A linear str.find scan on purpose: the regex `<!--.*?-->` is O(n^2) when a body carries many
    openers with no closer, which a hostile 20 MB track file could use to hang the nightly run.
    """
    if opener not in text:
        return text
    out: list[str] = []
    i = 0
    while True:
        start = text.find(opener, i)
        if start == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:start])
        end = text.find(closer, start + len(opener))
        if end == -1:
            return "".join(out)  # unterminated -- the remainder is not valid markup, drop it
        out.append(" ")
        i = end + len(closer)


def _strip_markup_noise(track: str) -> str:
    """Drop XML comments and CDATA: a <trkpt>/<coordinates> hidden in either is text, not a real point."""
    return _drop_spans(_drop_spans(track, "<!--", "-->"), "<![CDATA[", "]]>")


def _kml_linestring_bodies(track: str) -> list[str]:
    """The <coordinates> body of each <LineString>, found with a linear str.find scan.

    A KML often carries standalone <Point> placemarks and decorative or bounding-box lines besides
    the route, so the caller takes the longest of these. Each body is read only from within its own
    <LineString>..</LineString>, so an empty line cannot borrow a following <Polygon>'s boundary ring,
    and the scan is O(n) rather than the O(n^2) a `<LineString>.*?<coordinates>` regex would be.
    """
    low = track.lower()
    bodies: list[str] = []
    i = 0
    while True:
        ls = low.find("<linestring", i)
        if ls == -1:
            return bodies
        close = low.find("</linestring>", ls)
        seg_end = close if close != -1 else len(low)
        co = low.find("<coordinates", ls)
        if co != -1 and co < seg_end:
            co_gt = low.find(">", co)
            if co_gt != -1 and co_gt < seg_end:
                ce = low.find("</coordinates>", co_gt)
                if ce != -1 and ce <= seg_end:
                    bodies.append(track[co_gt + 1 : ce].strip())
        i = seg_end + len("</linestring>") if close != -1 else len(low)


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
    track = _strip_markup_noise(track)
    point = _gpx_start(track) or _kml_start(track)
    if point is None:
        return None
    lat, lng = point
    if -90 <= lat <= 90 and -180 <= lng <= 180 and (lat, lng) != (0.0, 0.0):
        return lat, lng
    return None


def _gpx_start(track: str) -> tuple[float, float] | None:
    """The first (lat, lng) of a GPX track/route point, reading lat and lon in either order.

    The tag's attributes are read from the match end up to the closing ``>`` found with str.find, so
    the work stays linear even on a file of unterminated tags.
    """
    for match in _GPX_TRKPT.finditer(track):
        gt = track.find(">", match.end())
        if gt == -1:
            return None  # a truncated tag: no complete point follows it either
        attrs = track[match.end() : gt]
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
    for body in _kml_linestring_bodies(track):
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


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether an address must never be connected to -- loopback, private, link-local, reserved.

    The single definition of "not a public host", shared by the URL gate here and the fetch's
    per-connection guard so the two can never drift apart (a link-local address is how a link reaches
    a cloud-metadata endpoint; private/loopback reach internal services).
    """
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def is_fetchable_track_url(url: str) -> bool:
    """Whether ``url`` is safe to download: http(s) to a host that resolves only to public IPs.

    The track URL comes from a page that may be hostile (an aggregator can link anything), so this
    is the SSRF gate: no file:// or other schemes, and no host that resolves to a loopback, private,
    link-local or otherwise reserved address. It is a first check on the name; the fetch re-validates
    the actual IP it connects to, so a host that rebinds to a private address after this passes is
    still refused at connect time.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return not any(is_blocked_ip(ipaddress.ip_address(sockaddr[0])) for *_, sockaddr in infos)


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
