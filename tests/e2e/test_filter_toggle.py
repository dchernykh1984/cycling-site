"""One button for the filters on a phone, with the number in force (issue #330)."""

import re

import pytest
from playwright.sync_api import Page, ViewportSize, expect

PHONE: ViewportSize = {"width": 390, "height": 844}
PAGES = ("/ru/calendar/", "/ru/calendar/list/", "/ru/calendar/map/")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", PAGES)
def test_a_phone_folds_the_filters_behind_one_button(page: Page, live_server, path):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}{path}")
    expect(page.locator("#filter-toggle")).to_be_visible()
    # The whole card folds away: no empty bordered box left where the filters were.
    expect(page.locator("#filter-panel")).to_be_hidden()
    expect(page.locator("#filter-panel .card")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", PAGES)
def test_a_wide_screen_shows_the_filters_without_the_button(page: Page, live_server, path):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}{path}")
    expect(page.locator("#filter-panel")).to_be_visible()
    expect(page.locator("#filter-toggle")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_the_button_counts_the_filters_in_force(page: Page, live_server, race_event_type):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/ru/calendar/list/?event_type={race_event_type.pk}")
    # The number on the icon, and in its words for a screen reader.
    expect(page.locator("#filter-toggle .filter-count")).to_have_text("1")
    expect(page.locator("#filter-toggle")).to_have_attribute("aria-label", re.compile(r"\(1\)$"))


@pytest.mark.django_db(transaction=True)
def test_no_filter_no_number(page: Page, live_server):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/ru/calendar/")
    expect(page.locator("#filter-toggle .filter-count")).to_be_hidden()
    expect(page.locator("#filter-toggle")).not_to_have_attribute("aria-label", re.compile(r"\("))


@pytest.mark.django_db(transaction=True)
def test_an_opened_panel_stays_open_after_the_list_reloads(page: Page, live_server, race_event_type):
    """The list reloads on every choice; folding shut each time sent the reader back to the button."""
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/ru/calendar/list/")
    page.locator("#filter-toggle").click()
    expect(page.locator("#filter-panel")).to_be_visible()
    page.goto(f"{live_server.url}/ru/calendar/list/?event_type={race_event_type.pk}")
    expect(page.locator("#filter-panel")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_orange_filter_icon_answers_a_44px_wide_tap(page: Page, live_server, settings):
    settings.DEFAULT_SKIN = "orange"
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/ru/calendar/")
    page.evaluate("() => document.fonts.ready")
    box = page.locator("#filter-toggle").bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + box["width"] / 2 - 21, box["y"] + box["height"] / 2)
    expect(page.locator("#filter-panel")).to_be_visible()
