"""The line an event's route file draws on its map, whatever the file's format (calendar_app.tracks)."""

import datetime
import io
import json
import shutil
import tempfile
import zipfile
from unittest import mock

from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, override_settings

from calendar_app import tracks
from calendar_app.models import Competition, CompetitionTrack

# Points far enough apart (about a kilometre) that thinning keeps every one.
RIDE = [(43.25, 76.95), (43.26, 76.96), (43.25, 76.97), (43.26, 76.98)]
GEOJSON_RIDE = [[lng, lat] for lat, lng in RIDE]


def _gpx(body: str) -> bytes:
    return f'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">{body}</gpx>'.encode()


def _points(tag: str, points) -> str:
    return "".join(f'<{tag} lat="{lat}" lon="{lng}"><ele>800</ele></{tag}>' for lat, lng in points)


def _kml(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2" '
        f'xmlns:gx="http://www.google.com/kml/ext/2.2"><Document>{body}</Document></kml>'
    ).encode()


def _kml_coordinates(points) -> str:
    return " ".join(f"{lng},{lat},800" for lat, lng in points)


def _tcx(points) -> bytes:
    trackpoints = "".join(
        f"<Trackpoint><Position><LatitudeDegrees>{lat}</LatitudeDegrees>"
        f"<LongitudeDegrees>{lng}</LongitudeDegrees></Position></Trackpoint>"
        for lat, lng in points
    )
    return (
        '<?xml version="1.0"?><TrainingCenterDatabase '
        'xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Courses><Course>'
        f"<Name>Ride</Name><Track>{trackpoints}</Track>"
        "<CoursePoint><Position><LatitudeDegrees>10</LatitudeDegrees><LongitudeDegrees>10</LongitudeDegrees>"
        "</Position></CoursePoint></Course></Courses></TrainingCenterDatabase>"
    ).encode()


def _fit(points, *, order="little", developer=False, compressed=False) -> bytes:
    """A FIT activity: a file_id message, then a record with a position for every point.

    ``compressed`` writes every other record with a compressed timestamp header, as some devices do;
    ``developer`` gives the records a developer field the reader has to step over.
    """
    arch = b"\x01" if order == "big" else b"\x00"
    body = bytearray()
    body += bytes([0x40 | 2, 0]) + arch + (0).to_bytes(2, order) + bytes([1, 0, 1, 0x00])  # file_id
    body += bytes([2, 4])
    fields = bytes([253, 4, 0x86, 0, 4, 0x85, 1, 4, 0x85])  # timestamp, latitude, longitude
    body += bytes([0x40 | (0x20 if developer else 0), 0]) + arch + (20).to_bytes(2, order) + bytes([3]) + fields
    if developer:
        body += bytes([1, 0, 2, 0])  # one developer field, two bytes long
    if compressed:
        body += bytes([0x40 | 1, 0]) + arch + (20).to_bytes(2, order) + bytes([2, 0, 4, 0x85, 1, 4, 0x85])
    for i, (lat, lng) in enumerate(points):
        position = b"".join(round(v / 180 * 2**31).to_bytes(4, order, signed=True) for v in (lat, lng))
        if compressed and i % 2:
            body += bytes([0x80 | 1 << 5 | i & 0x1F]) + position
        else:
            body += bytes([0]) + (1000 + i).to_bytes(4, order) + position + (b"\x00\x00" if developer else b"")
    header = bytes([14, 0x20]) + (2132).to_bytes(2, "little") + len(body).to_bytes(4, "little") + b".FIT\x00\x00"
    return header + bytes(body) + b"\x00\x00"


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _lines(data: bytes):
    geometry = tracks.read(data)
    return None if geometry is None else geometry["coordinates"]


class ReadTests(SimpleTestCase):
    def test_a_gpx_track_becomes_a_geojson_line_longitude_first(self):
        geometry = tracks.read(_gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>"))
        self.assertEqual(geometry, {"type": "MultiLineString", "coordinates": [GEOJSON_RIDE]})

    def test_every_segment_is_a_line_of_its_own(self):
        body = f"<trk><trkseg>{_points('trkpt', RIDE[:2])}</trkseg><trkseg>{_points('trkpt', RIDE[2:])}</trkseg></trk>"
        self.assertEqual(_lines(_gpx(body)), [GEOJSON_RIDE[:2], GEOJSON_RIDE[2:]])

    def test_a_gpx_file_without_tracks_draws_its_routes_and_one_with_tracks_only_those(self):
        route = f"<rte>{_points('rtept', RIDE[:2])}</rte>"
        track = f"<trk><trkseg>{_points('trkpt', RIDE[2:])}</trkseg></trk>"
        self.assertEqual(_lines(_gpx(route)), [GEOJSON_RIDE[:2]])
        self.assertEqual(_lines(_gpx(route + track)), [GEOJSON_RIDE[2:]])

    def test_waypoints_and_a_lone_point_are_not_drawn(self):
        body = f"{_points('wpt', [(1, 1)])}<trk><trkseg>{_points('trkpt', [(2, 2)])}</trkseg></trk>"
        self.assertIsNone(tracks.read(_gpx(body)))

    def test_kml_lines_are_drawn_and_its_points_and_areas_are_not(self):
        body = (
            f"<Placemark><Point><coordinates>{_kml_coordinates([(1, 1)])}</coordinates></Point></Placemark>"
            f"<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>{_kml_coordinates(RIDE)}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
            f"<Placemark><MultiGeometry><LineString><coordinates>\n  {_kml_coordinates(RIDE[:2])}\n"
            f"</coordinates></LineString><LineString><coordinates>{_kml_coordinates(RIDE[2:])}"
            "</coordinates></LineString></MultiGeometry></Placemark>"
        )
        self.assertEqual(_lines(_kml(body)), [GEOJSON_RIDE[:2], GEOJSON_RIDE[2:]])

    def test_a_kml_gx_track_is_drawn(self):
        coords = "".join(f"<gx:coord>{lng} {lat} 800</gx:coord>" for lat, lng in RIDE)
        self.assertEqual(_lines(_kml(f"<Placemark><gx:Track>{coords}</gx:Track></Placemark>")), [GEOJSON_RIDE])

    def test_a_kmz_is_read_as_what_its_bytes_say_whatever_its_name(self):
        kml = _kml(
            f"<Placemark><LineString><coordinates>{_kml_coordinates(RIDE)}</coordinates></LineString></Placemark>"
        )
        kmz = _zip({"doc.kml": kml, "files/photo.jpg": b"\xff\xd8\xff\xe0 not a track"})
        self.assertEqual(_lines(kmz), [GEOJSON_RIDE])

    def test_a_tcx_course_is_drawn_without_its_course_points(self):
        self.assertEqual(_lines(_tcx(RIDE)), [GEOJSON_RIDE])

    def test_a_fit_file_gives_the_positions_of_its_records(self):
        self.assertEqual(_lines(_fit(RIDE)), [GEOJSON_RIDE])
        self.assertEqual(_lines(_fit(RIDE, developer=True)), [GEOJSON_RIDE])

    def test_a_big_endian_fit_file_with_compressed_timestamps_is_read_too(self):
        self.assertEqual(_lines(_fit(RIDE, order="big", compressed=True)), [GEOJSON_RIDE])

    def test_a_fit_file_cut_short_keeps_the_line_up_to_the_cut(self):
        whole = _fit(RIDE)
        self.assertEqual(_lines(whole[:-15]), [GEOJSON_RIDE[:3]])  # the last record and the CRC are gone

    def test_geojson_lines_are_drawn_and_its_points_are_not(self):
        document = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}},
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": GEOJSON_RIDE[:2]}},
                {"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [GEOJSON_RIDE[2:]]}},
            ],
        }
        self.assertEqual(_lines(json.dumps(document).encode()), [GEOJSON_RIDE[:2], GEOJSON_RIDE[2:]])

    def test_an_archive_of_one_track_in_several_formats_draws_it_once(self):
        gpx = _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>")
        archive = _zip({"ride.fit": _fit(RIDE), "ride.tcx": _tcx(RIDE), "ride.gpx": gpx})
        self.assertEqual(_lines(archive), [GEOJSON_RIDE])

    def test_an_archive_of_several_distances_draws_each(self):
        short = _gpx(f"<trk><trkseg>{_points('trkpt', RIDE[:2])}</trkseg></trk>")
        long = _gpx(f"<trk><trkseg>{_points('trkpt', RIDE[2:])}</trkseg></trk>")
        self.assertEqual(_lines(_zip({"50km.gpx": short, "100km.gpx": long})), [GEOJSON_RIDE[:2], GEOJSON_RIDE[2:]])

    def test_an_archive_inside_an_archive_and_mac_leftovers_are_not_opened(self):
        gpx = _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>")
        self.assertIsNone(tracks.read(_zip({"inner.zip": _zip({"ride.gpx": gpx}), "__MACOSX/ride.gpx": gpx})))

    def test_a_file_declaring_entities_is_no_track(self):
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
            b'<gpx><trk><trkseg><trkpt lat="1" lon="1"/><trkpt lat="2" lon="2"/></trkseg></trk>&b;</gpx>'
        )
        self.assertIsNone(tracks.read(bomb))

    def test_files_that_hold_no_track_draw_nothing(self):
        for data in (
            b"",
            b"%PDF-1.7 a route map",
            b"\xff\xd8\xff\xe0 a photo of the route",
            b"<gpx><trk><trkseg><trkpt lat=",  # cut short
            b"<html><body>not a track</body></html>",
            b"[1, 2]",
            b'{"type": "LineString", "coordinates": "1,2 3,4"}',
            b"PK\x03\x04 a broken archive",
            b"0123456789AB.FIT but nothing after it",
        ):
            with self.subTest(data=data[:20]):
                self.assertIsNone(tracks.read(data))

    def test_points_off_the_earth_are_dropped(self):
        body = _points("trkpt", [(91, 1), (1, 181), (0, 0), ("nan", 1), RIDE[0], ("x", 2), RIDE[1]])
        self.assertEqual(_lines(_gpx(f"<trk><trkseg>{body}</trkseg></trk>")), [GEOJSON_RIDE[:2]])

    def test_a_thinned_line_keeps_its_ends_and_corners_and_drops_the_straight_between(self):
        straight = [(43.25, 76.95 + i * 0.001) for i in range(11)]  # 10 steps of 80 m along a parallel
        corner = [*straight, (43.26, 76.96)]
        self.assertEqual(
            _lines(_gpx(f"<trk><trkseg>{_points('trkpt', corner)}</trkseg></trk>")),
            [[[76.95, 43.25], [76.96, 43.25], [76.96, 43.26]]],
        )

    def test_a_long_line_is_thinned_to_what_a_page_can_carry(self):
        zigzag = [(43.25 + (i % 2) * 0.01, 76.0 + i * 0.001) for i in range(6000)]
        lines = _lines(_gpx(f"<trk><trkseg>{_points('trkpt', zigzag)}</trkseg></trk>")) or [[]]
        self.assertLessEqual(sum(map(len, lines)), tracks._MAX_POINTS_KEPT)
        self.assertEqual(lines[0][0], [76.0, 43.25])
        self.assertEqual(lines[0][-1], [round(76.0 + 5999 * 0.001, 5), 43.26])

    def test_reading_stops_once_enough_points_are_read(self):
        kml = f"<Placemark><LineString><coordinates>{_kml_coordinates(RIDE)}</coordinates></LineString></Placemark>"
        files = {
            "gpx": _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>"),
            "kml": _kml(kml),
            "tcx": _tcx(RIDE),
            "fit": _fit(RIDE),
            "geojson": json.dumps({"type": "LineString", "coordinates": GEOJSON_RIDE}).encode(),
        }
        with mock.patch.object(tracks, "_MAX_POINTS_READ", 3):
            for kind, data in files.items():
                with self.subTest(kind=kind):
                    self.assertEqual(_lines(data), [GEOJSON_RIDE[:3]])

    def test_a_geojson_nested_past_reason_is_read_no_deeper(self):
        node: dict = {"type": "LineString", "coordinates": GEOJSON_RIDE}
        for _ in range(40):
            node = {"type": "GeometryCollection", "geometries": [node]}
        self.assertIsNone(tracks.read(json.dumps(node).encode()))

    def test_the_tolerance_doubles_until_the_points_fit(self):
        # Off the straight by 7 m and back: kept at 5 m, gone at 10 m.
        wiggle = [(43.25 + (i % 2) * 7 / 111_320, 76.0 + i * 0.001) for i in range(30)]
        with mock.patch.object(tracks, "_MAX_POINTS_KEPT", 10):
            self.assertEqual(len(tracks._thinned([wiggle])[0]), 2)
        self.assertGreater(len(tracks._thinned([wiggle])[0]), 10)  # what 5 m keeps, over the cap

    def test_a_line_shaped_to_tire_the_thinning_keeps_every_nth_point_instead(self):
        zigzag = [(43.25 + (i % 2) * 0.01, 76.0 + i * 0.001) for i in range(50)]
        with mock.patch.object(tracks, "_WORK", 10), mock.patch.object(tracks, "_MAX_POINTS_KEPT", 10):
            lines = _lines(_gpx(f"<trk><trkseg>{_points('trkpt', zigzag)}</trkseg></trk>")) or [[]]
        self.assertLessEqual(len(lines[0]), 10)
        self.assertEqual((lines[0][0], lines[0][-1]), ([76.0, 43.25], [76.049, 43.26]))

    def test_every_pass_of_the_thinning_draws_on_one_budget(self):
        """A file that needs pass after pass stops at the budget rather than spending it on each one."""
        # Off a straight line by every distance up to a kilometre: each doubling of the tolerance
        # drops only some of the points, so the thinning goes pass after pass.
        zigzag = [(43.25 + (i * 7919 % 1000) / 111_320, 76.0 + i * 0.0001) for i in range(3000)]
        measured = []
        real = tracks._farthest

        def farthest(xy, first, last):
            measured.append(last - first)
            return real(xy, first, last)

        with (
            mock.patch.object(tracks, "_farthest", farthest),
            mock.patch.object(tracks, "_WORK", 50_000),
            mock.patch.object(tracks, "_MAX_POINTS_KEPT", 100),
        ):
            lines = tracks._thinned([zigzag])
        self.assertLessEqual(sum(measured), 50_000)
        self.assertLessEqual(sum(map(len, lines)), 100)

    def test_a_file_over_the_size_limit_is_not_read(self):
        gpx = _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>")
        with mock.patch.object(tracks, "MAX_BYTES", len(gpx) - 1):
            self.assertIsNone(tracks.read(gpx))


class RouteTrackTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        settings = override_settings(MEDIA_ROOT=media)
        settings.enable()
        self.addCleanup(settings.disable)
        self.competition = Competition.objects.create(title="Ride", date_start=datetime.date(2026, 11, 7))

    def _attach(self, name: str, data: bytes) -> None:
        self.competition.file_route.save(name, ContentFile(data))

    def test_an_event_without_a_route_file_has_no_track(self):
        self.assertIsNone(tracks.route_track(self.competition))
        self.assertFalse(CompetitionTrack.objects.exists())

    def test_the_file_is_read_once_and_then_kept(self):
        self._attach("ride.gpx", _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>"))
        with mock.patch.object(tracks, "read", wraps=tracks.read) as reader:
            first = tracks.route_track(self.competition)
            again = tracks.route_track(Competition.objects.get(pk=self.competition.pk))
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(first, again)
        self.assertEqual(first["coordinates"], [GEOJSON_RIDE])

    def test_a_new_file_is_read_on_the_next_visit(self):
        self._attach("ride.gpx", _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>"))
        tracks.route_track(self.competition)
        self._attach(
            "ride.kml",
            _kml(
                f"<Placemark><LineString><coordinates>{_kml_coordinates(RIDE[:2])}"
                "</coordinates></LineString></Placemark>"
            ),
        )
        self.assertEqual(tracks.route_track(self.competition)["coordinates"], [GEOJSON_RIDE[:2]])
        self.assertEqual(CompetitionTrack.objects.get().source, self.competition.file_route.name)

    def test_a_line_an_older_reader_kept_is_read_again(self):
        self._attach("ride.gpx", _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>"))
        CompetitionTrack.objects.create(
            competition=self.competition, source=self.competition.file_route.name, reader=tracks.READER - 1
        )
        self.assertEqual(tracks.route_track(self.competition)["coordinates"], [GEOJSON_RIDE])
        self.assertEqual(CompetitionTrack.objects.get().reader, tracks.READER)

    def test_a_file_that_holds_no_track_is_not_read_again(self):
        self._attach("route.pdf", b"%PDF-1.7 a route map")
        with mock.patch.object(tracks, "read", wraps=tracks.read) as reader:
            self.assertIsNone(tracks.route_track(self.competition))
            self.assertIsNone(tracks.route_track(self.competition))
        self.assertEqual(reader.call_count, 1)
        self.assertIsNone(CompetitionTrack.objects.get().geometry)

    def test_a_file_missing_from_the_disk_keeps_nothing_so_the_next_visit_tries_again(self):
        self.competition.file_route.name = "competitions/routes/gone.gpx"
        self.assertIsNone(tracks.route_track(self.competition))
        self.assertFalse(CompetitionTrack.objects.exists())

    def test_two_visits_at_once_both_get_the_track(self):
        self._attach("ride.gpx", _gpx(f"<trk><trkseg>{_points('trkpt', RIDE)}</trkseg></trk>"))
        with mock.patch.object(CompetitionTrack.objects, "update_or_create", side_effect=IntegrityError):
            self.assertEqual(tracks.route_track(self.competition)["coordinates"], [GEOJSON_RIDE])
