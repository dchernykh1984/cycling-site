"""E2E tests for the competition calendar view (FullCalendar)."""

import datetime

import pytest
from django.utils.formats import date_format
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect


@pytest.mark.django_db(transaction=True)
def test_a_wide_screen_opens_on_the_month_grid(page: Page, live_server):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_phone_opens_on_days_and_month_opens_the_grid(page: Page, live_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    page.locator('[data-period-kind="month"]').click()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_resizing_retains_the_calendar_layout(page: Page, live_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/en/calendar/")
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    page.set_viewport_size({"width": 1280, "height": 900})
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    page.locator('[data-period-kind="month"]').click()
    page.set_viewport_size({"width": 390, "height": 844})
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


@pytest.mark.django_db(transaction=True)
def test_month_arrows_retain_the_phone_layout(page: Page, live_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/en/calendar/")
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    page.locator('[data-period-step="1"]').click()
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    page.goto(f"{live_server.url}/en/calendar/")
    expect(page.locator(".fc-listRange-view")).to_be_visible()
    page.locator('[data-period-kind="month"]').click()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    page.locator('[data-period-step="1"]').click()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_grid_weekdays_use_the_readers_catalogue(page: Page, live_server, language):
    monday = datetime.date(2001, 1, 1)
    with translation_override(language):
        names = [date_format(monday + datetime.timedelta(days=n), "D") for n in range(7)]
    if language == "en":
        names = names[-1:] + names[:-1]
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/{language}/calendar/")
    expect(page.locator(".fc-col-header-cell")).to_have_text(names)
