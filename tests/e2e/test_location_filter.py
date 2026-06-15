"""E2E tests for the multi-select location filter on the competition list page (issue #108).

Each level (country/region/city/location) is a Bootstrap dropdown of checkboxes; lower
levels merge children of all selected parents and de-duplicate by name. Selecting a
checkbox auto-submits the list form with one ?location= param per selected id.
"""

import pytest
from playwright.sync_api import Page, expect

_LIST_URL = "/calendar/list/"
_DATES = "date_from=2026-07-01&date_to=2026-07-31"


@pytest.mark.django_db(transaction=True)
def test_country_dropdown_has_checkbox_options(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")).to_have_count(1)
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['ru'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_hidden_node_absent_from_dropdown(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['hidden'].pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_region_dropdown_disabled_before_country_chosen(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    expect(page.locator("#mf-btn-2")).to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_selecting_country_auto_submits_and_populates_region(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    page.click("#mf-btn-1")
    with page.expect_navigation():
        page.check(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")
    assert f"location={location_tree['kz'].pk}" in page.url
    page.click("#mf-btn-2")
    expect(page.locator(f"#mf-menu-2 input[value='{location_tree['region'].pk}']")).to_have_count(1)
    expect(page.locator("#mf-btn-2")).not_to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_filter_by_single_country_narrows_results(
    page: Page, live_server, kz_competition, ru_competition, location_tree
):
    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}&{_DATES}")
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).not_to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_multiselect_two_countries_shows_both(page: Page, live_server, kz_competition, ru_competition, location_tree):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}&location={location_tree['ru'].pk}&{_DATES}"
    page.goto(url)
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_country_checkbox_restored_from_url(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}")
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")).to_be_checked()


@pytest.mark.django_db(transaction=True)
def test_select_all_master_checkbox_selects_every_country(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    page.click("#mf-btn-1")
    with page.expect_navigation():
        page.check("#mf-menu-1 input.mf-all")
    assert f"location={location_tree['kz'].pk}" in page.url
    assert f"location={location_tree['ru'].pk}" in page.url


@pytest.mark.django_db(transaction=True)
def test_hidden_fallback_venue_shown_at_location_level(page: Page, live_server, location_tree):
    # Restore down to the city so the location level is populated; the hidden fallback
    # venue must appear there even though it is hidden elsewhere.
    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['city'].pk}")
    expect(page.locator("#mf-btn-4")).not_to_be_disabled()
    page.click("#mf-btn-4")
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['hidden'].pk}']")).to_have_count(1)
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['real'].pk}']")).to_have_count(1)
