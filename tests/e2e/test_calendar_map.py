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
from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING, open_filter_panel

# The map's own date filter is what these tests drive, so they take the suite's shared relative
# dates rather than keeping a second copy of them that could drift.


def _mapped_competition(organizer, title="Mapped Race", disciplines=None, event_type=None):
    loc = Location.add_root(
        name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709"
    )
    comp = Competition.objects.create(
        title_ru=title,
        date_start=UPCOMING,
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
    page.goto(f"{live_server.url}/ru/calendar/map/")
    expect(page.locator("#calendar-map")).to_have_count(1)
    expect(page.locator("#view-link-calendar")).to_have_count(1)
    expect(page.locator("#view-link-list")).to_have_count(1)
    expect(page.locator("#view-link-map")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_map_view_button_is_active_on_map_page(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/map/")
    expect(page.locator("#view-link-map")).to_have_class(re.compile(r"active"))


@pytest.mark.django_db(transaction=True)
def test_calendar_page_switches_to_map(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/")
    with page.expect_navigation():
        page.click("#view-link-map")
    assert "/ru/calendar/map/" in page.url


@pytest.mark.django_db(transaction=True)
def test_list_page_switches_to_map(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/list/")
    with page.expect_navigation():
        page.click("#view-link-map")
    assert "/ru/calendar/map/" in page.url


@pytest.mark.django_db(transaction=True)
def test_map_marker_popup_links_to_competition(page: Page, live_server, organizer):
    _mapped_competition(organizer)
    page.goto(f"{live_server.url}/ru/calendar/map/?{AROUND_UPCOMING}")
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
    page.goto(f"{live_server.url}/ru/calendar/map/")
    expect(page.locator("#calendar-map")).to_have_count(1)
    expect(page.locator(".leaflet-marker-icon")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_map_keeps_its_view_when_filters_change(page: Page, live_server, organizer):
    # Changing a filter must update the markers in place without resetting the user's pan/zoom.
    _mapped_competition(organizer)  # 90 days out, Almaty
    page.goto(f"{live_server.url}/ru/calendar/map/?{AROUND_UPCOMING}")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(1)  # initial load fits to the marker
    # User pans/zooms somewhere specific.
    page.wait_for_function("() => window.calendarMap")
    page.evaluate("() => window.calendarMap.setView([50.0, 60.0], 6)")
    # Narrow the date filter so the result set changes: end the range the day before the event, so
    # it drops out whenever the suite runs. On mobile the filter panel is collapsed, so expand it
    # before touching the date input.
    open_filter_panel(page)
    page.fill("#map-date-to", f"{UPCOMING - datetime.timedelta(days=1):%Y-%m-%d}")
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
    page.goto(f"{live_server.url}/ru/calendar/map/")
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


def _competition_at(organizer, name, lat, lng):
    loc = Location.add_root(name=name, name_ru=name, name_kk=name, name_en=name, lat=lat, lng=lng)
    Competition.objects.create(
        title_ru=f"Race in {name}",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=loc,
    )
    return loc


def _shows(page: Page, lat: float, lng: float) -> bool:
    return page.evaluate(f"() => window.calendarMap.getBounds().contains([{lat}, {lng}])")


ALMATY = (43.238949, 76.889709)
ASTANA = (51.169392, 71.449074)


@pytest.mark.django_db(transaction=True)
def test_a_reader_from_almaty_gets_almaty_and_its_surroundings(page: Page, live_server, organizer):
    """Which corner of the city a ride starts in is the question, not which country."""
    almaty = _competition_at(organizer, "Almaty", *map(str, ALMATY))
    _competition_at(organizer, "Astana", *map(str, ASTANA))
    page.goto(f"{live_server.url}/ru/calendar/map/?{AROUND_UPCOMING}&location={almaty.pk}")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(2)
    page.wait_for_function("() => window.calendarMap.getZoom() >= 8")
    assert _shows(page, *ALMATY)
    assert _shows(page, 43.87, 77.07)  # Konaev, out at the reservoir
    assert not _shows(page, *ASTANA)


@pytest.mark.django_db(transaction=True)
def test_with_nothing_on_in_almaty_its_reader_still_gets_almaty(page: Page, live_server, organizer):
    """One race in Astana must not throw the reader out to the whole country; it is a zoom away."""
    almaty = Location.add_root(
        name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", lat=str(ALMATY[0]), lng=str(ALMATY[1])
    )
    _competition_at(organizer, "Astana", *map(str, ASTANA))
    page.goto(f"{live_server.url}/ru/calendar/map/?{AROUND_UPCOMING}&location={almaty.pk}")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(1)
    page.wait_for_function("() => window.calendarMap.getZoom() >= 8")
    assert _shows(page, *ALMATY)
    assert not _shows(page, *ASTANA)


@pytest.mark.django_db(transaction=True)
def test_a_reader_from_elsewhere_gets_every_marker(page: Page, live_server, organizer):
    """No area is set up for Astana: the map fits what is on, as it always did."""
    _competition_at(organizer, "Almaty", *map(str, ALMATY))
    astana = _competition_at(organizer, "Astana", *map(str, ASTANA))
    page.goto(f"{live_server.url}/ru/calendar/map/?{AROUND_UPCOMING}&location={astana.pk}")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(2)
    page.wait_for_function(
        f"() => [{list(ASTANA)}, {list(ALMATY)}].every(p => window.calendarMap.getBounds().contains(p))"
    )


@pytest.mark.django_db(transaction=True)
def test_a_guest_with_no_place_gets_every_marker(page: Page, live_server, organizer):
    _competition_at(organizer, "Almaty", *map(str, ALMATY))
    _competition_at(organizer, "Astana", *map(str, ASTANA))
    page.goto(f"{live_server.url}/ru/calendar/map/?{AROUND_UPCOMING}&location=")
    expect(page.locator(".leaflet-marker-icon")).to_have_count(2)
    # Both at once: on a phone the fit is animated, and halfway through only one may be in view.
    page.wait_for_function(
        f"() => [{list(ASTANA)}, {list(ALMATY)}].every(p => window.calendarMap.getBounds().contains(p))"
    )
