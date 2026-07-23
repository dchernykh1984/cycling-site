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

    coord = start_coordinate(["https://8.8.8.8/2026/brm.kml"], fake_fetch)
    assert coord == (49.80972, 73.08371)
    assert calls == ["https://8.8.8.8/2026/brm.kml"]


def test_start_coordinate_swallows_a_fetch_error():
    def boom(url):
        raise OSError("network down")

    assert start_coordinate(["https://8.8.8.8/2026/brm.kml"], boom) is None


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


def test_kml_start_is_the_line_not_a_point_placemark():
    """A KML overview/finish <Point> before the route <LineString> must not be taken as the start."""
    kml = (
        "<kml>"
        "<Placemark><Point><coordinates>76.889709,43.238949,0</coordinates></Point></Placemark>"
        "<Placemark><LineString><coordinates>73.08371,49.80972,0 73.2,49.9,0</coordinates></LineString></Placemark>"
        "</kml>"
    )
    assert parse_start(kml) == (49.80972, 73.08371)


def test_kml_without_a_linestring_yields_nothing():
    assert (
        parse_start("<kml><Placemark><Point><coordinates>73.0,49.0,0</coordinates></Point></Placemark></kml>") is None
    )


def test_ssrf_gate_rejects_private_and_metadata_hosts():
    from agent.geo import is_fetchable_track_url

    # A public host is allowed; loopback / link-local (cloud metadata) / private are refused, as is
    # a non-http scheme.
    assert is_fetchable_track_url("http://127.0.0.1/x.gpx") is False
    assert is_fetchable_track_url("http://169.254.169.254/latest/meta-data/x.gpx") is False
    assert is_fetchable_track_url("http://10.0.0.5/x.gpx") is False
    assert is_fetchable_track_url("file:///etc/passwd") is False
    assert is_fetchable_track_url("ftp://example.test/x.gpx") is False


def test_start_coordinate_refuses_an_unsafe_url_without_fetching():
    calls: list[str] = []

    def spy(url):
        calls.append(url)
        return "<gpx><trkpt lat='1' lon='2'></trkpt></gpx>"

    link = "https://route.eduha.info/?load=http%3A%2F%2F169.254.169.254%2Fx.gpx"
    assert start_coordinate([link], spy) is None
    assert calls == []  # the SSRF gate blocks it before any fetch


def test_track_url_rejects_trailing_junk_after_the_extension():
    assert track_url(["https://route.eduha.info/?load=https%3A%2F%2Fevil.test%2Fa.gpxINJECTED"]) is None


def test_redirect_to_a_private_host_is_refused():
    """A public decoy that 302s to a metadata/internal address must not be followed."""
    import urllib.error

    from agent.fetch import _NoUnsafeRedirect

    handler = _NoUnsafeRedirect()

    class _Req:
        def get_full_url(self):
            return "https://decoy.public/route.gpx"

    try:
        handler.redirect_request(_Req(), None, 302, "Found", {}, "http://169.254.169.254/x.gpx")
        raise AssertionError("redirect to a private host should have raised")
    except urllib.error.URLError:
        pass


def test_kml_takes_the_longest_linestring_as_the_route():
    """A short decorative/overview LineString before the route must not be taken as the start."""
    kml = (
        "<kml>"
        "<Placemark><LineString><coordinates>10.0,80.0,0 11.0,81.0,0</coordinates></LineString></Placemark>"
        "<Placemark><LineString><coordinates>"
        "73.08371,49.80972,0 73.1,49.85,0 73.2,49.9,0 73.3,49.95,0"
        "</coordinates></LineString></Placemark>"
        "</kml>"
    )
    assert parse_start(kml) == (49.80972, 73.08371)


def test_parse_start_ignores_a_commented_or_cdata_decoy_point():
    """A <trkpt> hidden in a comment or CDATA is text, not the route; the real first point wins."""
    commented = (
        '<gpx><!-- <trkpt lat="10.0" lon="20.0"></trkpt> -->'
        '<trk><trkseg><trkpt lat="49.80972" lon="73.08371"/></trkseg></trk></gpx>'
    )
    assert parse_start(commented) == (49.80972, 73.08371)
    cdata = (
        '<gpx><trk><name><![CDATA[<trkpt lat="10.0" lon="20.0"></trkpt>]]></name>'
        '<trkseg><trkpt lat="49.80972" lon="73.08371"/></trkseg></trk></gpx>'
    )
    assert parse_start(cdata) == (49.80972, 73.08371)


def test_kml_empty_linestring_does_not_borrow_a_polygon_boundary():
    """An empty <LineString> must not reach into a following <Polygon> ring for its coordinates."""
    kml = (
        "<kml>"
        "<Placemark><LineString></LineString></Placemark>"
        "<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
        "30.0,60.0,0 31.0,61.0,0 32.0,62.0,0 33.0,63.0,0 34.0,64.0,0 35.0,65.0,0"
        "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        "<Placemark><LineString><coordinates>"
        "73.08371,49.80972,0 73.1,49.85,0 73.2,49.9,0"
        "</coordinates></LineString></Placemark>"
        "</kml>"
    )
    assert parse_start(kml) == (49.80972, 73.08371)


def test_gpx_attribute_order_and_namespace_do_not_matter():
    """lon-before-lat and a namespace prefix are valid GPX and must still parse."""
    assert parse_start('<gpx><trkpt lon="73.08371" lat="49.80972"></trkpt></gpx>') == (49.80972, 73.08371)
    assert parse_start('<gpx:gpx><gpx:trkpt lat="49.80972" lon="73.08371"/></gpx:gpx>') == (49.80972, 73.08371)


def test_kml_gx_track_export_is_read():
    """A Google/Strava <gx:Track> stores the path in <gx:coord> as 'lon lat alt', no LineString."""
    kml = "<kml><gx:Track><gx:coord>73.08371 49.80972 0</gx:coord><gx:coord>73.2 49.9 0</gx:coord></gx:Track></kml>"
    assert parse_start(kml) == (49.80972, 73.08371)
