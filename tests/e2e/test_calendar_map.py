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

# The map's own date filter is what these tests drive, so the dates are relative to the day the
# suite runs. Written as fixed dates they were a time bomb: the "hidden because the range excludes
# it" test placed its event 30 days and one day out, and started failing the morning the calendar's
# default 30-day window reached it.
_EVENT_DAY = datetime.date.today() + datetime.timedelta(days=90)
_FORTNIGHT = datetime.timedelta(days=14)
_AROUND_THE_EVENT = f"date_from={_EVENT_DAY - _FORTNIGHT:%Y-%m-%d}&date_to={_EVENT_DAY + _FORTNIGHT:%Y-%m-%d}"


def _mapped_competition(organizer, title="Mapped Race", disciplines=None, event_type=None):
    loc = Location.add_root(
        name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709"
    )
    comp = Competition.objects.create(
        title_ru=title,
        date_start=_EVENT_DAY,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=loc,
    )
    if disciplines:
        comp.disciplines.set(disciplines)
    if event_type is not None:
        comp.event_types.set([event_type])
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
    page.goto(f"{live_server.url}/calendar/map/?{_AROUND_THE_EVENT}")
    marker = page.locator(".leaflet-marker-icon")
    expect(marker).to_have_count(1)
    marker.click()
    popup = page.locator(".leaflet-popup-content")
    expect(popup).to_contain_text("Mapped Race")
    expect(popup.locator("a")).to_have_attribute("target", "_blank")


@pytest.mark.django_db(transaction=True)
def test_map_marker_hidden_when_date_range_excludes_competition(page: Page, live_server, organizer):
    _mapped_competition(organizer)
    # The default range is the next 30 days; the event sits 90 days out, so no marker is drawn.
    page.goto(f"{live_server.url}/calendar/map/")
    expect(page.locator("#calendar-map")).to_have_count(1)
    expect(page.locator(".leaflet-marker-icon")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_map_keeps_its_view_when_filters_change(page: Page, live_server, organizer):
    # Changing a filter must update the markers in place without resetting the user's pan/zoom.
    _mapped_competition(organizer)  # 90 days out, Almaty
    page.goto(f"{live_server.url}/calendar/map/?{_AROUND_THE_EVENT}")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(1)  # initial load fits to the marker
    # User pans/zooms somewhere specific.
    page.wait_for_function("() => window.calendarMap")
    page.evaluate("() => window.calendarMap.setView([50.0, 60.0], 6)")
    # Narrow the date filter so the result set changes: end the range the day before the event, so
    # it drops out whenever the suite runs. On mobile the filter panel is collapsed, so expand it
    # before touching the date input.
    open_filter_panel(page)
    page.fill("#map-date-to", f"{_EVENT_DAY - datetime.timedelta(days=1):%Y-%m-%d}")
    page.dispatch_event("#map-date-to", "change")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(0)  # markers refreshed in place
    # ...but the map view stayed exactly where the user left it (no re-fit / no reset to default).
    view = page.evaluate(
        "() => ({z: window.calendarMap.getZoom(), lat: window.calendarMap.getCenter().lat,"
        " lng: window.calendarMap.getCenter().lng})"
    )
    assert view["z"] == 6, view
    assert abs(view["lat"] - 50.0) < 0.5 and abs(view["lng"] - 60.0) < 0.5, view


@pytest.mark.django_db(transaction=True)
def test_map_filter_dropdown_renders_above_zoom_controls(page: Page, live_server, road_category):
    # Regression: the Leaflet zoom (+/-) / layer controls (z-index ~1000) used to show through the
    # open filter dropdown on mobile. The filter dropdowns must stack above the map controls.
    page.goto(f"{live_server.url}/calendar/map/")
    expect(page.locator(".leaflet-control-zoom")).to_have_count(1)  # map initialised
    open_filter_panel(page)  # collapsed on mobile
    page.click("#dd-btn-1")  # open the direction dropdown
    expect(page.locator("#dd-menu-1")).to_be_visible()
    z = page.evaluate(
        "() => { const zi = el => el ? (parseInt(getComputedStyle(el).zIndex) || 0) : -1;"
        " return {menu: zi(document.querySelector('#dd-menu-1')),"
        " ctrl: zi(document.querySelector('.leaflet-top'))}; }"
    )
    assert z["menu"] > z["ctrl"], z
