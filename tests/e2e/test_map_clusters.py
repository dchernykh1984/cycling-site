"""Places that crowd the calendar map gather into one numbered cluster a finger can hit (#387).

The places are made up and lie in the South Atlantic, a hundred metres apart.
"""

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from locations.models import Location
from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING


def _event_at(organizer, name, lat, lng):
    place = Location.add_root(name=name, name_ru=name, name_kk=name, name_en=name, lat=lat, lng=lng)
    Competition.objects.create(
        title_ru=f"{name} Race",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=place,
    )


def _assert_tappable(locator):
    box = locator.bounding_box()
    assert box is not None and box["width"] >= 44 - 0.5 and box["height"] >= 44 - 0.5, box


@pytest.mark.django_db(transaction=True)
def test_two_places_a_street_apart_are_one_cluster_that_opens_into_two_pins(page: Page, live_server, organizer):
    _event_at(organizer, "Quay", "-40.000000", "-20.000000")
    _event_at(organizer, "Pier", "-40.000900", "-20.000000")
    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/en/calendar/map/?{AROUND_UPCOMING}")

    cluster = page.locator(".map-cluster")
    expect(cluster).to_have_count(1)
    expect(cluster).to_have_text("2 places close together; zoom in to see them")
    # What a screen reader announces: the count first, as the reader sees it, then what it is.
    expect(page.get_by_role("button", name="2 places close together; zoom in to see them")).to_have_count(1)
    _assert_tappable(cluster)

    cluster.click()
    pins = page.locator(".map-pin")
    expect(pins).to_have_count(2)
    expect(page.locator(".map-cluster")).to_have_count(0)
    for i in range(2):
        _assert_tappable(pins.nth(i))
    expect(page.get_by_role("button", name="Pier", exact=True)).to_have_count(1)  # a pin is named by its place
    # The pin answers in its square, not along its shadow, which reaches 7 px further right.
    square = page.locator(".map-pin[title='Quay']").bounding_box()
    assert square is not None
    hit = page.evaluate(
        "([x, y]) => document.elementFromPoint(x, y).closest('.map-pin')?.title || null",
        [square["x"] + square["width"] + 3, square["y"] + square["height"] - 4],
    )
    assert hit != "Quay", hit

    page.locator(".map-pin[title='Quay']").click()
    expect(page.locator(".leaflet-popup-content")).to_contain_text("Quay Race")
