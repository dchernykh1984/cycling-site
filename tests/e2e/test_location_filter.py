"""E2E tests for the multi-select location filter on the competition list page (issue #108).

Each level (country/region/city/location) is a Bootstrap dropdown of checkboxes; lower
levels merge children of all selected parents and de-duplicate by name. Selecting a
checkbox auto-submits the list form, which carries the selected ids as one
comma-joined ?location= value.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import AROUND_UPCOMING

_LIST_URL = "/calendar/list/"
# The fixtures are dated from the day the suite runs (conftest.UPCOMING), so the range that has to
# contain them is built the same way rather than pinned to a month that eventually passes.
_DATES = AROUND_UPCOMING


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
    # The ids travel as one comma-joined value, so that hundreds of countries cannot overrun the
    # request line the server accepts (tests/e2e/test_filter_url_length.py).
    selected = set(parse_qs(urlsplit(page.url).query)["location"][0].split(","))
    assert {str(location_tree["kz"].pk), str(location_tree["ru"].pk)} <= selected


@pytest.mark.django_db(transaction=True)
def test_hidden_fallback_venue_shown_at_location_level(page: Page, live_server, location_tree):
    # Restore down to the city so the location level is populated; the hidden fallback
    # venue must appear there even though it is hidden elsewhere.
    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['city'].pk}")
    expect(page.locator("#mf-btn-4")).not_to_be_disabled()
    page.click("#mf-btn-4")
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['hidden'].pk}']")).to_have_count(1)
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['real'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_search_box_filters_checkboxes_case_insensitively(page: Page, live_server, location_tree):
    # The country dropdown has a type-to-filter box: typing shows only the checkboxes whose name
    # contains the text (case-insensitive); clearing it restores all.
    page.goto(f"{live_server.url}{_LIST_URL}")
    page.click("#mf-btn-1")
    search = page.locator("#mf-menu-1 .mf-search")
    expect(search).to_have_count(1)
    kz_row = page.locator(f"#mf-menu-1 li.mf-item-row:has(input[value='{location_tree['kz'].pk}'])")
    ru_row = page.locator(f"#mf-menu-1 li.mf-item-row:has(input[value='{location_tree['ru'].pk}'])")
    expect(kz_row).to_be_visible()
    expect(ru_row).to_be_visible()

    search.fill("kz")  # lower-case query matches "KZ"
    expect(kz_row).to_be_visible()
    expect(ru_row).to_be_hidden()

    search.fill("")
    expect(kz_row).to_be_visible()
    expect(ru_row).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_hidden_country_is_selectable_in_filter(page: Page, live_server, location_tree):
    # Issue #113: a hidden real country/region/city stays selectable in the filter
    # (hidden matters only for the virtual "other location" venue).
    from locations.models import Location

    hidden_country = Location.add_root(
        name="HiddenLand", name_ru="HiddenLand", name_kk="HiddenLand", name_en="HiddenLand", is_hidden=True
    )
    page.goto(f"{live_server.url}{_LIST_URL}")
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{hidden_country.pk}']")).to_have_count(1)
