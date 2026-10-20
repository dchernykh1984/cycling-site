"""The filters in force as chips with a cross, on a phone (issue #330)."""

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from tests.e2e.conftest import inject_session

PHONE: ViewportSize = {"width": 390, "height": 844}


@pytest.mark.django_db(transaction=True)
def test_a_chip_names_the_filter_and_its_choice(page: Page, live_server, race_event_type):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/en/calendar/list/?event_type={race_event_type.pk}")
    chip = page.locator("#filter-chips .filter-chip")
    expect(chip).to_have_count(1)
    expect(chip).to_contain_text("Event type: Race")


@pytest.mark.django_db(transaction=True)
def test_the_cross_lifts_the_filter_on_the_list(page: Page, live_server, race_event_type):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/en/calendar/list/?event_type={race_event_type.pk}")
    page.locator("#filter-chips .filter-chip").click()
    page.wait_for_url(lambda url: "event_type" not in url)
    expect(page.locator("#filter-chips .filter-chip")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_the_cross_lifts_the_filter_on_the_calendar(page: Page, live_server, race_event_type):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/en/calendar/?event_type={race_event_type.pk}")
    expect(page.locator("#filter-toggle")).to_contain_text("(1)")
    page.locator("#filter-chips .filter-chip").click()
    expect(page.locator("#filter-chips .filter-chip")).to_have_count(0)
    expect(page.locator("#filter-toggle")).not_to_contain_text("(")


@pytest.mark.django_db(transaction=True)
def test_no_filter_no_chips(page: Page, live_server):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/en/calendar/")
    expect(page.locator("#filter-chips .filter-chip")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_wide_screen_has_the_panel_and_no_chips(page: Page, live_server, race_event_type):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}/en/calendar/list/?event_type={race_event_type.pk}")
    expect(page.locator("#filter-chips")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_the_favourites_chip_unticks_the_box(page: Page, live_server, superuser):
    page.set_viewport_size(PHONE)
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/en/calendar/list/?favorite=1")
    chip = page.locator("#filter-chips .filter-chip")
    expect(chip).to_contain_text("Only favorites")
    chip.click()
    page.wait_for_url(lambda url: "favorite" not in url)
    expect(page.locator("#filter-chips .filter-chip")).to_have_count(0)
