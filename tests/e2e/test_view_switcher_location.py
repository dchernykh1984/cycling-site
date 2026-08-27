"""E2E regression: the view switcher must preserve the location filter across the map.

The map view has no location filter of its own (it *is* the location view), so it has to carry the
incoming ``?location=`` params through its switcher links. Before the fix it dropped them, so
switching List/Calendar -> Map -> back silently reset the location filter (while the date range,
persisted separately, survived). These tests pin that the location filter now survives a map
round-trip.
"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import AROUND_UPCOMING

# The fixtures are dated from the day the suite runs (conftest.UPCOMING), so the range that has to
# contain them is built the same way rather than pinned to a month that eventually passes.
_DATES = AROUND_UPCOMING


@pytest.mark.django_db(transaction=True)
def test_map_switcher_links_keep_location(page: Page, live_server, location_tree):
    """On the map, the links back to the list and calendar must retain the ?location param."""
    kz = location_tree["kz"].pk
    page.goto(f"{live_server.url}/ru/calendar/map/?location={kz}")
    for link_id in ("#view-link-list", "#view-link-calendar"):
        expect(page.locator(link_id)).to_have_attribute("href", re.compile(rf"[?&]location={kz}(&|$)"))


@pytest.mark.django_db(transaction=True)
def test_location_filter_survives_map_round_trip_to_list(
    page: Page, live_server, kz_competition, ru_competition, location_tree
):
    """List (filtered by KZ) -> Map -> List keeps the KZ-only result set."""
    kz = location_tree["kz"].pk
    page.goto(f"{live_server.url}/ru/calendar/list/?location={kz}&{_DATES}")
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).not_to_contain_text("RU Race")

    # Wait for the list JS to populate the map switcher link, then go to the map.
    expect(page.locator("#view-link-map")).to_have_attribute("href", re.compile(rf"location={kz}"))
    with page.expect_navigation():
        page.click("#view-link-map")

    # The map's own link back to the list must carry the location param (the fix).
    expect(page.locator("#view-link-list")).to_have_attribute("href", re.compile(rf"location={kz}"))
    with page.expect_navigation():
        page.click("#view-link-list")

    assert f"location={kz}" in page.url
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).not_to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_location_checkbox_restored_after_map_round_trip(page: Page, live_server, location_tree):
    """After List -> Map -> List the country checkbox is still checked (filter visibly retained)."""
    kz = location_tree["kz"].pk
    page.goto(f"{live_server.url}/ru/calendar/list/?location={kz}&{_DATES}")
    expect(page.locator("#view-link-map")).to_have_attribute("href", re.compile(rf"location={kz}"))
    with page.expect_navigation():
        page.click("#view-link-map")
    expect(page.locator("#view-link-list")).to_have_attribute("href", re.compile(rf"location={kz}"))
    with page.expect_navigation():
        page.click("#view-link-list")
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{kz}']")).to_be_checked()
