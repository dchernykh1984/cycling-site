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
from tests.e2e.conftest import open_filter_panel

_SEPT = "date_from=2026-09-01&date_to=2026-09-30"


def _mapped_competition(organizer, title="Mapped Race", disciplines=None, event_type=None):
    loc = Location.add_root(
        name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709"
    )
    comp = Competition.objects.create(
        title_ru=title,
        date_start=datetime.date(2026, 9, 15),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=loc,
        event_type=event_type,
    )
    if disciplines:
        comp.disciplines.set(disciplines)
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


@pytest.mark.django_db(transaction=True)
def test_map_keeps_its_view_when_filters_change(page: Page, live_server, organizer):
    # Changing a filter must update the markers in place without resetting the user's pan/zoom.
    _mapped_competition(organizer)  # 2026-09-15, Almaty
    page.goto(f"{live_server.url}/calendar/map/?{_SEPT}")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(1)  # initial load fits to the marker
    # User pans/zooms somewhere specific.
    page.wait_for_function("() => window.calendarMap")
    page.evaluate("() => window.calendarMap.setView([50.0, 60.0], 6)")
    # Narrow the date filter so the result set changes (the Sept event drops out). On mobile the
    # filter panel is collapsed, so expand it before touching the date input.
    open_filter_panel(page)
    page.fill("#map-date-to", "2026-09-10")
    page.dispatch_event("#map-date-to", "change")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(0)  # markers refreshed in place
    # ...but the map view stayed exactly where the user left it (no re-fit / no reset to default).
    view = page.evaluate(
        "() => ({z: window.calendarMap.getZoom(), lat: window.calendarMap.getCenter().lat,"
        " lng: window.calendarMap.getCenter().lng})"
    )
    assert view["z"] == 6, view
    assert abs(view["lat"] - 50.0) < 0.5 and abs(view["lng"] - 60.0) < 0.5, view
