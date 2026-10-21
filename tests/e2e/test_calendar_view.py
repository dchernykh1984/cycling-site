"""E2E tests for the competition calendar view (FullCalendar)."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db(transaction=True)
def test_a_wide_screen_opens_on_the_month_grid(page: Page, live_server):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_phone_opens_on_the_list_of_days(page: Page, live_server):
    """Seven columns of one-word titles on a 390px screen read as noise (issue #330)."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc-listMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_reader_switches_the_view_and_it_is_kept(page: Page, live_server):
    """Chosen once and remembered -- never switched by the page on its own (the address bar of a
    phone sliding away fires a resize, and a view that followed resizes jumped about)."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/ru/calendar/")
    page.locator('[data-month-view="dayGridMonth"]').click()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 700})
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    page.reload()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", ("/ru/calendar/", "/ru/calendar/list/", "/ru/calendar/map/"))
def test_no_tab_scrolls_sideways_on_a_phone(page: Page, live_server, path):
    """The rows above the content are nearly the width of a phone screen and must wrap.

    Unwrapped, the calendar's toolbar once measured 456px inside a 388px container on a Pixel 7 and
    took the whole document out to 468px in a 412px screen: every page scrolled sideways.
    """
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}{path}")
    expect(page.locator("#period-nav")).to_be_visible()
    widths = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert widths[0] <= widths[1], f"the page overflows: {widths[0]}px in {widths[1]}px"


@pytest.mark.django_db(transaction=True)
def test_switching_tabs_moves_none_of_the_controls(page: Page, live_server):
    """Calendar, list and map share one header: a tap on a tab must not make the buttons jump."""
    page.set_viewport_size({"width": 390, "height": 844})
    controls = (
        "#filter-toggle",
        "#view-link-calendar",
        "#view-link-list",
        "#view-link-map",
        '[data-period-kind="days"]',
        '[data-period-kind="month"]',
        '[data-period-step="-1"]',
        '[data-period-step="1"]',
        "#period-label",
        "[data-period-today]",
    )
    boxes = {}
    for path in ("/ru/calendar/", "/ru/calendar/list/", "/ru/calendar/map/"):
        page.goto(f"{live_server.url}{path}")
        expect(page.locator("#period-nav")).to_be_visible()
        boxes[path] = [page.locator(selector).bounding_box() for selector in controls]
    calendar, listing, mapping = boxes.values()
    assert calendar == listing == mapping, boxes
