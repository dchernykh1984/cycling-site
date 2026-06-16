"""E2E tests for the calendar Map view and the 3-button view switcher (issue #107).

The map shows a marker per location that has competitions matching the filters
(date range + event type + direction/discipline); clicking a marker opens a popup
listing those competitions as links (opening in a new tab) with their dates.
"""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from locations.models import Location

_SEPT = "date_from=2026-09-01&date_to=2026-09-30"


def _mapped_competition(organizer, title="Mapped Race", discipline=None, event_type=None):
    loc = Location.add_root(
        name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709"
    )
    Competition.objects.create(
        title_ru=title,
        date_start=datetime.date(2026, 9, 15),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=loc,
        discipline=discipline,
        event_type=event_type,
    )
    return loc


@pytest.mark.django_db(transaction=True)
def test_map_page_renders_with_three_view_buttons(page: Page, live_server):
    page.goto(f"{live_server.url}/calendar/map/")
    expect(page.locator("#calendar-map")).to_have_count(1)
    expect(page.locator("#view-link-calendar")).to_have_count(1)
    expect(page.locator("#view-link-list")).to_have_count(1)
    expect(page.locator("#view-link-map")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_map_view_button_is_active_on_map_page(page: Page, live_server):
    page.goto(f"{live_server.url}/calendar/map/")
    expect(page.locator("#view-link-map")).to_have_class(re.compile(r"active"))


@pytest.mark.django_db(transaction=True)
def test_calendar_page_switches_to_map(page: Page, live_server):
    page.goto(f"{live_server.url}/calendar/")
    with page.expect_navigation():
        page.click("#view-link-map")
    assert "/calendar/map/" in page.url


@pytest.mark.django_db(transaction=True)
def test_list_page_switches_to_map(page: Page, live_server):
    page.goto(f"{live_server.url}/calendar/list/")
    with page.expect_navigation():
        page.click("#view-link-map")
    assert "/calendar/map/" in page.url


@pytest.mark.django_db(transaction=True)
def test_map_marker_popup_links_to_competition(page: Page, live_server, organizer):
    _mapped_competition(organizer)
    page.goto(f"{live_server.url}/calendar/map/?{_SEPT}")
    marker = page.locator(".leaflet-marker-icon")
    expect(marker).to_have_count(1)
    marker.click()
    popup = page.locator(".leaflet-popup-content")
    expect(popup).to_contain_text("Mapped Race")
    expect(popup.locator("a")).to_have_attribute("target", "_blank")


@pytest.mark.django_db(transaction=True)
def test_map_marker_hidden_when_date_range_excludes_competition(page: Page, live_server, organizer):
    _mapped_competition(organizer)
    # Default range is the next 30 days from today (2026-06); the Sept event is out of range.
    page.goto(f"{live_server.url}/calendar/map/")
    expect(page.locator("#calendar-map")).to_have_count(1)
    expect(page.locator(".leaflet-marker-icon")).to_have_count(0)
