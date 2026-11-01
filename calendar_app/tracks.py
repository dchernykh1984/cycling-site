"""The line an event's route file draws on its map.

A route file is whatever an organizer's planner or device exports: GPX above all, KML and the
zipped KMZ of Google Earth, TCX and FIT from Garmin-style devices, GeoJSON from web maps, or a ZIP
holding any of them. ``read`` turns each into one GeoJSON MultiLineString small enough for a phone:
every track in the file -- or, in a GPX file with none, every planned route -- as a line, thinned to
a few metres. Waypoints, controls and areas are not drawn; only the lines are.

The kind of file is told from its bytes, never from its name: a ".gpx" that was really a KMZ has
been seen on an organizer's site. The file is the organizer's upload, so it is read as untrusted:
no XML entities, a cap on the bytes, the points and the work, and a file that breaks a reader is
simply no track.

``route_track`` reads an event's file on the first visit after it came and keeps what it found
(CompetitionTrack), so that a visit after that costs one query.
"""

from __future__ import annotations

import io
import json
import math
import re
import zipfile
from collections.abc import Callable, Iterator
from typing import Any, Literal

from defusedxml.ElementTree import iterparse
from django.db import IntegrityError, transaction

from calendar_app.models import CompetitionTrack

# What a route file may be named on the event form, beside the documents every file field takes.
EXTENSIONS = frozenset({"gpx", "kml", "kmz", "tcx", "fit", "geojson"})

MAX_BYTES = 10 * 1024 * 1024  # what the event form takes; a larger file is not read
_MAX_POINTS_READ = 500_000  # from one file; the rest of a larger one is left unread
_MAX_LINES = 200
_MAX_POINTS_KEPT = 4_000  # sent to the page, over all its lines
_TOLERANCE = 5.0  # metres a thinned line may stray from the file's; doubled until the points fit
# Distances from a point to a segment the thinning may measure for one file, about a second's work; a
# file that needs more -- a huge one, or one shaped to make it -- keeps every n-th point instead.
_WORK = 4_000_000
_DIGITS = 5  # decimal places of a degree kept: about a metre
_METRES_PER_DEGREE = 111_320.0

Line = list[tuple[float, float]]  # (lat, lng) points


class _EnoughPointsError(Exception):
    """Enough points have been read from the file."""


class _OutOfWorkError(Exception):
    """The thinning has spent the work one file may take."""


class _Lines:
    """Points gathered into lines as a file gives them; a line of fewer than two points is none."""

    def __init__(self) -> None:
        self.lines: list[Line] = []
        self.count = 0

    def start(self) -> None:
        self.lines.append([])

    def add(self, lat, lng) -> None:
        point = _point(lat, lng)
        if point is None or not self.lines:
            return
        self.lines[-1].append(point)
        self.count += 1
        if self.count >= _MAX_POINTS_READ:
            raise _EnoughPointsError

    def found(self) -> list[Line]:
        return [line for line in self.lines if len(line) > 1]


def _point(lat, lng) -> tuple[float, float] | None:
    """A point on the earth, or None -- out of range, not a number, or the 0,0 a device writes for none."""
    try:
        point = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    # A NaN fails both ranges.
    if -90 <= point[0] <= 90 and -180 <= point[1] <= 180 and point != (0.0, 0.0):
        return point
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_events(data: bytes) -> Iterator[tuple[str, Any]]:
    return iterparse(io.BytesIO(data), events=("start", "end"))


def _gpx(data: bytes) -> list[Line]:
    """Every track segment; a file without tracks gives its routes instead."""
    tracks, routes = _Lines(), _Lines()
    current = tracks
    try:
        for event, element in _xml_events(data):
            name = _local(element.tag)
            if event == "start":
                if name in ("trk", "trkseg"):
                    current = tracks
                    tracks.start()
                elif name == "rte":
                    current = routes
                    routes.start()
            elif name in ("trkpt", "rtept"):
                current.add(element.get("lat"), element.get("lon"))
                element.clear()
            elif name in ("trkseg", "trk", "rte"):
                element.clear()
    except _EnoughPointsError:
        pass
    return tracks.found() or routes.found()


_AROUND_COMMA = re.compile(r"\s*,\s*")


def _kml(data: bytes) -> list[Line]:
    """Every LineString and gx:Track; the rings of a Polygon are areas, not routes."""
    lines = _Lines()
    open_line_strings = 0
    try:
        for event, element in _xml_events(data):
            name = _local(element.tag)
            if event == "start":
                if name in ("LineString", "Track"):  # Track: gx:Track, a line of gx:coord points
                    lines.start()
                open_line_strings += name == "LineString"
                continue
            if name == "LineString":
                open_line_strings -= 1
            elif name == "coordinates" and open_line_strings:
                _kml_coordinates(element.text, lines)
            elif name == "coord":
                lng, lat = [*str(element.text).split(), "", ""][:2]  # "lng lat alt"
                lines.add(lat, lng)
            element.clear()
    except _EnoughPointsError:
        pass
    return lines.found()


def _kml_coordinates(text, lines: _Lines) -> None:
    """A KML coordinates list: "lng,lat[,alt]" tuples apart by white space."""
    for pair in _AROUND_COMMA.sub(",", str(text or "")).split():
        lng, _, rest = pair.partition(",")
        lines.add(rest.partition(",")[0], lng)


def _tcx(data: bytes) -> list[Line]:
    """Every Track of an activity's laps or of a course; course points are not part of the line."""
    lines = _Lines()
    lat = lng = None
    try:
        for event, element in _xml_events(data):
            name = _local(element.tag)
            if event == "start":
                if name == "Track":
                    lines.start()
                elif name == "Trackpoint":
                    lat = lng = None
            elif name == "LatitudeDegrees":
                lat = element.text
            elif name == "LongitudeDegrees":
                lng = element.text
            elif name == "Trackpoint":
                lines.add(lat, lng)
                element.clear()
    except _EnoughPointsError:
        pass
    return lines.found()


# A FIT file is a header and messages, each defined by an earlier definition message of the same
# local number. A record message (global number 20) carries the position as semicircles in its
# fields 0 (latitude) and 1 (longitude); everything else is skipped by the sizes its definition gives.
_FIT_RECORD = 20
_FIT_NO_VALUE = 0x7FFFFFFF
_SEMICIRCLE = 180 / 2**31

_Order = Literal["big", "little"]
_FitDefinition = tuple[_Order, int, list[tuple[int, int]], int]  # byte order, message, fields, developer bytes


def _fit(data: bytes) -> list[Line]:
    """The records' positions as one line."""
    lines = _Lines()
    lines.start()
    header = data[0]
    end = min(len(data), header + int.from_bytes(data[4:8], "little"))
    definitions: dict[int, _FitDefinition] = {}
    position = header
    try:
        while position < end:
            position = _fit_message(data, position, definitions, lines)
    except (IndexError, KeyError, _EnoughPointsError):
        pass  # a file cut short keeps the line read up to the cut
    return lines.found()


def _fit_message(data: bytes, position: int, definitions: dict[int, _FitDefinition], lines: _Lines) -> int:
    record = data[position]
    position += 1
    if record & 0x80:  # a compressed timestamp header: a data message of local type 0-3
        return _fit_data(data, position, definitions[(record >> 5) & 0x03], lines)
    if record & 0x40:
        position, definitions[record & 0x0F] = _fit_definition(data, position, bool(record & 0x20))
        return position
    return _fit_data(data, position, definitions[record & 0x0F], lines)


def _fit_definition(data: bytes, position: int, developer: bool) -> tuple[int, _FitDefinition]:
    order: _Order = "big" if data[position + 1] == 1 else "little"
    message = int.from_bytes(data[position + 2 : position + 4], order)
    count = data[position + 4]
    position += 5
    fields = [(data[position + 3 * i], data[position + 3 * i + 1]) for i in range(count)]
    position += 3 * count
    developer_bytes = 0
    if developer:
        developer_count = data[position]
        developer_bytes = sum(data[position + 1 + 3 * i + 1] for i in range(developer_count))
        position += 1 + 3 * developer_count
    return position, (order, message, fields, developer_bytes)


def _fit_data(data: bytes, position: int, definition: _FitDefinition, lines: _Lines) -> int:
    order, message, fields, developer_bytes = definition
    found: dict[int, float] = {}
    for number, size in fields:
        if message == _FIT_RECORD and number in (0, 1) and size == 4:
            value = int.from_bytes(data[position : position + 4], order, signed=True)
            if value != _FIT_NO_VALUE:
                found[number] = value * _SEMICIRCLE
        position += size
    if len(found) == 2:
        lines.add(found[0], found[1])
    return position + developer_bytes


def _geojson(data: bytes) -> list[Line]:
    """Every LineString and MultiLineString, wherever it sits in the document."""
    lines = _Lines()
    try:
        _geojson_walk(json.loads(data.decode("utf-8-sig")), lines)
    except _EnoughPointsError:
        pass
    return lines.found()


def _geojson_walk(node, lines: _Lines, depth: int = 0) -> None:
    if not isinstance(node, dict) or depth > 32:
        return
    kind = str(node.get("type"))
    children = {"FeatureCollection": "features", "GeometryCollection": "geometries"}.get(kind)
    inside = node.get(children) if children else node.get("coordinates")
    if not isinstance(inside, list):
        if kind == "Feature":
            _geojson_walk(node.get("geometry"), lines, depth + 1)
    elif children:
        for child in inside:
            _geojson_walk(child, lines, depth + 1)
    elif kind == "LineString":
        _geojson_line(inside, lines)
    elif kind == "MultiLineString":
        for line in inside:
            _geojson_line(line, lines)


def _geojson_line(positions, lines: _Lines) -> None:
    lines.start()
    for position in positions if isinstance(positions, list) else []:
        if isinstance(position, list) and len(position) >= 2:
            lines.add(position[1], position[0])  # GeoJSON writes longitude first


def _zip(data: bytes) -> list[Line]:
    """The lines of the archive's track files, KMZ included.

    Several formats of one track are often packed together; their lines are drawn once, from the
    format first in _ARCHIVE_ORDER. Several files of one format -- the distances of a race -- are
    all drawn. An archive inside the archive is not opened.
    """
    found: dict[str, list[Line]] = {}
    budget = MAX_BYTES
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.file_size > budget or info.filename.startswith("__MACOSX/"):
                continue
            budget -= info.file_size
            with archive.open(info) as member:
                inner = member.read(info.file_size + 1)
            kind = _kind(inner)
            if kind in _READERS and len(inner) <= info.file_size:
                found.setdefault(kind, []).extend(_READERS[kind](inner))
    return next((found[kind] for kind in _ARCHIVE_ORDER if found.get(kind)), [])


_XML_KINDS = {"gpx": "gpx", "kml": "kml", "TrainingCenterDatabase": "tcx"}


def _kind(data: bytes) -> str | None:
    """Which reader the bytes are for: "zip", "fit", "geojson", "gpx", "kml", "tcx", or None."""
    if data[:4] == b"PK\x03\x04":
        return "zip"
    if len(data) >= 12 and data[8:12] == b".FIT":
        return "fit"
    head = data[:256].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head[:1] == b"{":
        return "geojson"
    if head[:1] != b"<":
        return None
    try:
        _, root = next(iter(_xml_events(data)))
    except Exception:  # not well-formed XML is no track either
        return None
    return _XML_KINDS.get(_local(root.tag))


_READERS: dict[str, Callable[[bytes], list[Line]]] = {
    "gpx": _gpx,
    "kml": _kml,
    "tcx": _tcx,
    "fit": _fit,
    "geojson": _geojson,
}
_ARCHIVE_ORDER = ("gpx", "kml", "tcx", "geojson", "fit")


def read(data: bytes) -> dict | None:
    """The file's lines as a GeoJSON MultiLineString, or None when it holds none to draw."""
    if len(data) > MAX_BYTES:
        return None
    kind = _kind(data)
    try:
        lines = _zip(data) if kind == "zip" else _READERS[kind](data) if kind in _READERS else []
    except Exception:  # whatever breaks a reader, the page draws nothing and keeps its button
        return None
    lines = _thinned(lines[:_MAX_LINES])
    if not lines:
        return None
    return {
        "type": "MultiLineString",
        "coordinates": [[[round(lng, _DIGITS), round(lat, _DIGITS)] for lat, lng in line] for line in lines],
    }


def _thinned(lines: list[Line]) -> list[Line]:
    """The lines with as few points as keep them within the tolerance, at most _MAX_POINTS_KEPT in all.

    The tolerance doubles until the points fit. All of it shares one budget of _WORK: past it, every
    n-th point of what the last pass left is kept instead, which costs one pass.
    """
    budget = [_WORK]
    tolerance = _TOLERANCE
    try:
        while True:
            lines = [_douglas_peucker(line, tolerance, budget) for line in lines]
            if sum(map(len, lines)) <= _MAX_POINTS_KEPT:
                return lines
            tolerance *= 2
    except _OutOfWorkError:
        # Room is left for each line's last point, which is kept whatever the step.
        step = -(-sum(map(len, lines)) // max(1, _MAX_POINTS_KEPT - len(lines)))
        return [line[::step] if (len(line) - 1) % step == 0 else [*line[::step], line[-1]] for line in lines]


def _douglas_peucker(line: Line, tolerance: float, budget: list[int]) -> Line:
    """The line's points that matter, by Douglas and Peucker: none of the rest strays past tolerance.

    Distances are measured on a plane laid over the line's middle latitude, near enough for a line's
    own extent; each one measured is taken from the budget.
    """
    if len(line) < 3:
        return line
    scale = math.cos(math.radians(sum(lat for lat, _ in line) / len(line))) * _METRES_PER_DEGREE
    xy = [(lng * scale, lat * _METRES_PER_DEGREE) for lat, lng in line]
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    spans = [(0, len(line) - 1)]
    while spans:
        first, last = spans.pop()
        budget[0] -= last - first
        if budget[0] < 0:
            raise _OutOfWorkError
        index, distance = _farthest(xy, first, last)
        if distance > tolerance:
            keep[index] = True
            spans += [(first, index), (index, last)]
    return [point for point, kept in zip(line, keep, strict=True) if kept]


def _farthest(xy: list[tuple[float, float]], first: int, last: int) -> tuple[int, float]:
    """The point between first and last farthest from the segment joining them, and its distance."""
    ax, ay = xy[first]
    dx, dy = xy[last][0] - ax, xy[last][1] - ay
    length = dx * dx + dy * dy
    index, farthest = first, 0.0
    for i in range(first + 1, last):
        px, py = xy[i][0] - ax, xy[i][1] - ay
        t = min(1.0, max(0.0, (px * dx + py * dy) / length)) if length else 0.0
        distance = (px - t * dx) ** 2 + (py - t * dy) ** 2
        if distance > farthest:
            index, farthest = i, distance
    return index, math.sqrt(farthest)


def route_track(competition) -> dict | None:
    """The line the event's route file draws, or None when it has no file or the file draws none."""
    name = competition.file_route.name
    if not name:
        return None
    kept = CompetitionTrack.objects.filter(competition=competition).first()
    if kept is not None and kept.source == name:
        return kept.geometry
    try:
        with competition.file_route.open("rb") as file:
            data = file.read(MAX_BYTES + 1)
    except OSError:
        return None  # not readable just now: nothing is kept, so the next visit tries again
    geometry = read(data)
    try:
        with transaction.atomic():
            CompetitionTrack.objects.update_or_create(
                competition=competition, defaults={"source": name, "geometry": geometry}
            )
    except IntegrityError:
        pass  # a visit at the same moment kept it first
    return geometry
