"""Pulling a start coordinate out of a linked GPS track."""

from agent.geo import parse_start, start_coordinate, track_url

_GPX = (
    '<?xml version="1.0"?><gpx><trk><trkseg>'
    '<trkpt lat="49.80972" lon="73.08371"></trkpt>'
    '<trkpt lat="49.9" lon="73.2"></trkpt></trkseg></trk></gpx>'
)
_KML = (
    "<kml><Placemark><LineString>"
    "<coordinates>73.08371,49.80972,0 73.2,49.9,0</coordinates>"
    "</LineString></Placemark></kml>"
)


def test_track_url_prefers_a_direct_file():
    assert (
        track_url(["https://x.test/a", "https://r2.randonneurs.kz/2026/brm.kml"])
        == "https://r2.randonneurs.kz/2026/brm.kml"
    )


def test_track_url_unwraps_a_route_editor_link():
    link = "https://route.eduha.info/route-track-editor/?load=https%3A%2F%2Fr2.randonneurs.kz%2F2026%2Fbrm.kml"
    assert track_url([link]) == "https://r2.randonneurs.kz/2026/brm.kml"


def test_track_url_turns_a_ridewithgps_route_into_its_gpx_export():
    assert track_url(["https://ridewithgps.com/routes/53318000"]) == "https://ridewithgps.com/routes/53318000.gpx"


def test_track_url_none_when_no_track_link():
    assert track_url(["https://example.test/page", "https://t.me/chan"]) is None


def test_parse_start_reads_the_first_gpx_point_lat_then_lon():
    assert parse_start(_GPX) == (49.80972, 73.08371)


def test_parse_start_reads_the_first_kml_point_lon_then_lat():
    # KML stores lon,lat -- the parser must not swap the venue into the sea.
    assert parse_start(_KML) == (49.80972, 73.08371)


def test_parse_start_rejects_an_out_of_range_or_null_island_point():
    assert parse_start('<gpx><trkpt lat="999" lon="0"></trkpt></gpx>') is None
    assert parse_start("<kml><coordinates>0,0,0</coordinates></kml>") is None
    assert parse_start("<gpx></gpx>") is None


def test_start_coordinate_fetches_the_linked_track():
    calls: list[str] = []

    def fake_fetch(url):
        calls.append(url)
        return _KML

    coord = start_coordinate(["https://r2.randonneurs.kz/2026/brm.kml"], fake_fetch)
    assert coord == (49.80972, 73.08371)
    assert calls == ["https://r2.randonneurs.kz/2026/brm.kml"]


def test_start_coordinate_swallows_a_fetch_error():
    def boom(url):
        raise OSError("network down")

    assert start_coordinate(["https://r2.randonneurs.kz/2026/brm.kml"], boom) is None


def test_start_coordinate_none_without_a_track():
    assert start_coordinate(["https://example.test/x"], lambda url: "") is None


def test_gpx_start_is_the_track_not_a_waypoint():
    """GPX lists waypoints (finish/controls) before the track; the start is the first trkpt."""
    gpx = (
        "<gpx>"
        '<wpt lat="43.238949" lon="76.889709"><name>Finish</name></wpt>'
        "<trk><trkseg>"
        '<trkpt lat="49.80972" lon="73.08371"></trkpt>'
        '<trkpt lat="49.9" lon="73.2"></trkpt>'
        "</trkseg></trk></gpx>"
    )
    assert parse_start(gpx) == (49.80972, 73.08371)


def test_gpx_route_points_are_used_when_there_is_no_track():
    gpx = '<gpx><rte><rtept lat="49.80972" lon="73.08371"></rtept></rte></gpx>'
    assert parse_start(gpx) == (49.80972, 73.08371)
