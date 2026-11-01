"""An event's route file draws its track on the event's map, with arrows for the way it goes."""

import os
import re

import pytest
from django.core.files.base import ContentFile
from playwright.sync_api import Page, expect

# Westward from the start, then north, then east again: every arrow points the way the file runs.
TRACK = [(43.2390, 76.8897), (43.2390, 76.8600), (43.2600, 76.8600), (43.2600, 76.9100)]
GPX = (
    '<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
    + "".join(f'<trkpt lat="{lat}" lon="{lng}"/>' for lat, lng in TRACK)
    + "</trkseg></trk></gpx>"
).encode()
SCREENSHOTS = os.environ.get("E2E_SCREENSHOTS")  # a folder to look at the map in, when set


def _event(competition, venue, *, route: bytes, name: str):
    venue.lat, venue.lng = "43.238949", "76.889709"
    venue.save()
    competition.location = venue
    competition.url_route = "https://example.com/route"
    competition.file_route.save(name, ContentFile(route))
    competition.save()
    return competition


def _inside(inner, outer) -> bool:
    return (
        inner["x"] >= outer["x"] - 1
        and inner["y"] >= outer["y"] - 1
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + 1
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + 1
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [360, 1280])
def test_the_whole_track_and_the_start_are_in_view_with_arrows_the_way_it_runs(
    page: Page, live_server, kz_competition, location_tree, settings, tmp_path, width
):
    settings.MEDIA_ROOT = tmp_path
    event = _event(kz_competition, location_tree["real"], route=GPX, name="ride.gpx")
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server.url}/en/calendar/{event.pk}/")

    expect(page.locator("path.route-track")).to_have_count(1)
    expect(page.locator("path.route-track-arrow").first).to_be_attached()
    expect(page.locator("#competition-map-caption")).to_have_text("Arrows show the direction of the track.")
    page.wait_for_timeout(300)  # the opening view settles before its boxes are measured
    if SCREENSHOTS:
        page.locator("#competition-map").screenshot(path=f"{SCREENSHOTS}/route-track-{width}.png")

    map_box = page.locator("#competition-map").bounding_box()
    line_box = page.locator("path.route-track").bounding_box()
    marker_box = page.locator(".leaflet-marker-icon").bounding_box()
    assert map_box and line_box and marker_box
    assert _inside(line_box, map_box), (line_box, map_box)
    assert _inside(marker_box, map_box), (marker_box, map_box)

    # Each arrow is a chevron "M wing L tip L wing"; its tip lies ahead of its wings along the line.
    chevrons = page.eval_on_selector_all("path.route-track-arrow", "paths => paths.map(p => p.getAttribute('d'))")
    headings = set()
    for d in chevrons:
        (x1, y1), (tx, ty), (x2, y2) = [tuple(map(float, pair)) for pair in re.findall(r"(-?[\d.]+) (-?[\d.]+)", d)]
        dx, dy = tx - (x1 + x2) / 2, ty - (y1 + y2) / 2
        headings.add("west" if dx < -1 else "east" if dx > 1 else "north" if dy < -1 else "south")
    assert headings <= {"west", "north", "east"}, headings
    assert {"west", "east"} <= headings, headings

    # The line takes the colour its skin names.
    colours = page.evaluate(
        """() => {
            const probe = document.createElement('div');
            probe.style.color = 'var(--skin-route)';
            document.body.appendChild(probe);
            const named = getComputedStyle(probe).color;
            probe.remove();
            return [named, getComputedStyle(document.querySelector('path.route-track')).stroke];
        }"""
    )
    assert colours[0] == colours[1], colours


@pytest.mark.django_db(transaction=True)
def test_the_track_link_and_the_track_file_are_both_offered(
    page: Page, live_server, kz_competition, location_tree, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    event = _event(kz_competition, location_tree["real"], route=GPX, name="ride.gpx")
    page.goto(f"{live_server.url}/en/calendar/{event.pk}/")

    expect(page.locator("#route-link")).to_have_text("Link to the track")
    expect(page.locator("#route-link")).to_have_attribute("href", "https://example.com/route")
    expect(page.locator("#route-download")).to_have_text("Download the track")
    expect(page.locator("#route-download")).to_have_attribute("download", "")
    with page.expect_download() as download:
        page.locator("#route-download").click()
    assert download.value.suggested_filename.endswith(".gpx")


@pytest.mark.django_db(transaction=True)
def test_a_route_file_that_is_no_track_leaves_the_map_as_it_was(
    page: Page, live_server, kz_competition, location_tree, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    event = _event(kz_competition, location_tree["real"], route=b"%PDF-1.7 a route map", name="route.pdf")
    page.goto(f"{live_server.url}/en/calendar/{event.pk}/")

    expect(page.locator(".leaflet-marker-icon")).to_have_count(1)
    expect(page.locator("img.leaflet-tile[src*='/13/']").first).to_be_attached()
    expect(page.locator("path.route-track")).to_have_count(0)
    expect(page.locator("#competition-map-caption")).to_have_count(0)
    expect(page.locator("#route-file")).to_have_text("Route")
    expect(page.locator("#route-download")).to_have_count(0)
