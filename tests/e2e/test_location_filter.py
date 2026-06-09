"""E2E tests for the location cascade filter on the competition list page."""

import pytest
from playwright.sync_api import Page, expect

_LIST_URL = "/calendar/list/"
_DATE_PARAMS = "date_from=2026-07-01&date_to=2026-07-31"


# ---------------------------------------------------------------------------
# country dropdown populated from DB
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_location_country_dropdown_populated(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    # Both KZ and RU roots must appear as options (value = pk, text = name_ru)
    expect(page.locator(f"#flt-country option[value='{location_tree['kz'].pk}']")).to_have_count(1)
    expect(page.locator(f"#flt-country option[value='{location_tree['ru'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_location_hidden_nodes_absent_from_filter_dropdown(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    # The hidden depth-4 venue must not appear in the country dropdown
    expect(page.locator(f"#flt-country option[value='{location_tree['hidden'].pk}']")).to_have_count(0)


# ---------------------------------------------------------------------------
# cascade: selecting country populates region
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_location_region_select_disabled_before_country_chosen(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    expect(page.locator("#flt-region")).to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_location_region_populates_after_country_selected(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    with page.expect_navigation():
        page.select_option("#flt-country", str(location_tree["kz"].pk))
    # After navigation: region dropdown has the KZ region option
    expect(page.locator(f"#flt-region option[value='{location_tree['region'].pk}']")).to_have_count(1)
    expect(page.locator("#flt-region")).not_to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_location_filter_auto_submits_on_country_change(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    with page.expect_navigation():
        page.select_option("#flt-country", str(location_tree["kz"].pk))
    assert f"location={location_tree['kz'].pk}" in page.url


# ---------------------------------------------------------------------------
# filter actually narrows competitions
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_location_filter_by_country_shows_kz_competition(
    page: Page, live_server, kz_competition, ru_competition, location_tree
):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}&{_DATE_PARAMS}"
    page.goto(url)
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).not_to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_location_filter_by_country_shows_ru_competition(
    page: Page, live_server, kz_competition, ru_competition, location_tree
):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['ru'].pk}&{_DATE_PARAMS}"
    page.goto(url)
    expect(page.locator("body")).to_contain_text("RU Race")
    expect(page.locator("body")).not_to_contain_text("KZ Race")


@pytest.mark.django_db(transaction=True)
def test_location_filter_by_city_shows_only_city_competition(page: Page, live_server, kz_competition, location_tree):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['city'].pk}&{_DATE_PARAMS}"
    page.goto(url)
    expect(page.locator("body")).to_contain_text("KZ Race")


# ---------------------------------------------------------------------------
# pre-population from GET params
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_location_filter_prepopulates_country_from_url(page: Page, live_server, location_tree):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}"
    page.goto(url)
    # Country dropdown must have kz selected
    expect(page.locator("#flt-country")).to_have_value(str(location_tree["kz"].pk))


@pytest.mark.django_db(transaction=True)
def test_location_filter_prepopulates_region_from_url(page: Page, live_server, location_tree):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['region'].pk}"
    page.goto(url)
    expect(page.locator("#flt-country")).to_have_value(str(location_tree["kz"].pk))
    expect(page.locator("#flt-region")).to_have_value(str(location_tree["region"].pk))


@pytest.mark.django_db(transaction=True)
def test_location_filter_prepopulates_city_from_url(page: Page, live_server, location_tree):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['city'].pk}"
    page.goto(url)
    expect(page.locator("#flt-city")).to_have_value(str(location_tree["city"].pk))
