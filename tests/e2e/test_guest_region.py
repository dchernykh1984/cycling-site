"""E2E: a guest's calendar opens on their region, and a region they cleared stays cleared (#332).

The network provider's point is sent as the headers it would add; the places are made up and lie in
the South Atlantic, out of reach of the seeded real geography.
"""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import open_filter_panel


@pytest.fixture
def testland(db):
    from calendar_app.models import Competition
    from locations.models import add_location_child

    country = add_location_child(None, name="Testland", name_ru="Testland", name_kk="Testland", name_en="Testland")
    north = add_location_child(country, name="North", name_ru="North", name_kk="North", name_en="North")
    town = add_location_child(
        north,
        name="Northville",
        name_ru="Northville",
        name_kk="Northville",
        name_en="Northville",
        lat="-40.0",
        lng="-20.0",
    )
    square = add_location_child(town, name="Square", name_ru="Square", name_kk="Square", name_en="Square")
    Competition.objects.create(
        title_ru="Northville Race",
        date_start=datetime.date.today() + datetime.timedelta(days=5),
        status=Competition.Status.APPROVED,
        location=square,
    )
    return north


@pytest.mark.django_db(transaction=True)
def test_a_guest_opens_on_their_region_and_keeps_the_whole_calendar_once_they_clear_it(
    page: Page, live_server, testland
):
    page.set_extra_http_headers({"CF-IPLatitude": "-40.02", "CF-IPLongitude": "-20.02"})
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page).to_have_url(re.compile(rf"[?&]location={testland.pk}(&|$)"))
    open_filter_panel(page)
    page.click("#mf-btn-2")
    region = page.locator(f"#mf-menu-2 input[value='{testland.pk}']")
    expect(region).to_be_checked()

    with page.expect_navigation():
        region.uncheck()
    assert "location=" not in page.url

    # A fresh, bare address of another tab: the region was offered once this visit, and not again.
    page.goto(f"{live_server.url}/ru/calendar/")
    assert "location=" not in page.url
