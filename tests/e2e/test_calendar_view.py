"""E2E tests for the competition calendar view (FullCalendar)."""

import datetime

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
    page.locator(".fc-dayGridMonth-button").click()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 700})
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()
    page.reload()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_month_picker_sits_next_to_today_and_moves_the_grid(page: Page, live_server):
    """A race six years back used to be seventy clicks away; the picker is one."""
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc")).to_be_visible()

    left = page.locator(".fc-toolbar-chunk").first
    expect(left.locator(".fc-today-button")).to_be_visible()
    expect(left.locator("#calendar-month-picker")).to_be_visible()

    month = page.locator("#calendar-month-select")
    year = page.locator("#calendar-year-select")
    today = datetime.date.today()
    # The picker opens on the month the grid opened on.
    expect(month).to_have_value(str(today.month))
    expect(year).to_have_value(str(today.year))

    target = 3 if today.month != 3 else 6
    title = page.locator(".fc-toolbar-title")
    was = title.inner_text()
    month.select_option(str(target))
    expect(title).not_to_have_text(was)
    expect(title).to_contain_text(str(today.year))

    # And the grid moves the picker back.
    page.locator(".fc-next-button").click()
    expect(month).to_have_value(str(target + 1))


@pytest.mark.django_db(transaction=True)
def test_the_picker_follows_the_grid_past_the_years_it_lists(page: Page, live_server):
    """An empty calendar lists this year alone -- the arrows can still walk out of it."""
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc")).to_be_visible()
    year = page.locator("#calendar-year-select")
    today = datetime.date.today()
    steps = 13
    for _ in range(steps):
        page.locator(".fc-prev-button").click()
    landed = (today.year * 12 + today.month - 1 - steps) // 12
    expect(year).to_have_value(str(landed))


@pytest.mark.django_db(transaction=True)
def test_the_toolbar_does_not_widen_the_page(page: Page, live_server):
    """The picker joined a row that was already nearly the width of a phone screen.

    Unwrapped, the toolbar measured 456px inside a 388px container on a Pixel 7 and took the whole
    document out to 468px in a 412px screen: every page scrolled sideways from the calendar on.
    """
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc")).to_be_visible()
    widths = page.evaluate(
        "() => {const t = document.querySelector('.fc-header-toolbar'); return [t.scrollWidth, t.clientWidth];}"
    )
    assert widths[0] <= widths[1], f"the toolbar overflows: {widths[0]}px in {widths[1]}px"


@pytest.mark.django_db(transaction=True)
def test_the_picker_shares_the_row_with_the_buttons(page: Page, live_server):
    """Beside Today, not underneath it -- on a screen wide enough to hold both."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator(".fc")).to_be_visible()
    today = page.locator(".fc-today-button").bounding_box()
    picker = page.locator("#calendar-month-picker").bounding_box()
    assert today and picker
    assert picker["x"] > today["x"], "the picker should follow the Today button"
    # Same line: the two boxes overlap vertically.
    assert picker["y"] < today["y"] + today["height"]
    assert today["y"] < picker["y"] + picker["height"]
