"""E2E tests for the multi-select location filter on the competition list page (issue #108).

Each level (country/region/city/location) is a Bootstrap dropdown of checkboxes; lower
levels merge children of all selected parents and de-duplicate by name. Selecting a
checkbox auto-submits the list form, which carries the selected ids as one
comma-joined ?location= value.
"""

import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import AROUND_UPCOMING, open_filter_panel

_LIST_URL = "/ru/calendar/list/"
# The fixtures are dated from the day the suite runs (conftest.UPCOMING), so the range that has to
# contain them is built the same way rather than pinned to a month that eventually passes.
_DATES = AROUND_UPCOMING


@pytest.mark.django_db(transaction=True)
def test_country_dropdown_has_checkbox_options(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")).to_have_count(1)
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['ru'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_hidden_node_absent_from_dropdown(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['hidden'].pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_every_level_opens_before_the_one_above_is_chosen(page: Page, live_server, location_tree):
    """A place is looked for at its own level straight away, without picking a country first."""
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    for level in (2, 3, 4):
        expect(page.locator(f"#mf-btn-{level}")).to_be_enabled()
    page.click("#mf-btn-3")
    # By its name: the seeded geography alone is more cities than a menu draws.
    search = page.locator("#mf-menu-3 .mf-search")
    cities = page.locator("#mf-menu-3 li.mf-item-row")
    for city in ("Almaty", "Moscow"):
        search.fill(city)
        expect(cities.filter(has_text=city)).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_a_city_typed_under_a_chosen_country_comes_from_that_country_only(page: Page, live_server, location_tree):
    """The reported case: with Kazakhstan ticked, "Al" in the city finds Almaty and not Alabuga in Russia."""
    from locations.models import Location

    Location.objects.get(name_en="RU Region").add_child(
        name="Alabuga", name_ru="Alabuga", name_kk="Alabuga", name_en="Alabuga"
    )
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-3")
    page.locator("#mf-menu-3 .mf-search").fill("Al")
    cities = page.locator("#mf-menu-3 li.mf-item-row")
    expect(cities.filter(has_text="Alabuga")).to_have_count(1)  # nothing chosen: every country's

    page.click("#mf-btn-1")  # the menu open below closes as another opens
    with page.expect_navigation():
        page.check(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")
    open_filter_panel(page)
    page.click("#mf-btn-3")
    page.locator("#mf-menu-3 .mf-search").fill("Al")
    expect(cities.filter(has_text="Almaty")).to_have_count(1)
    expect(cities.filter(has_text="Alabuga")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_a_venue_is_typed_in_and_ticked_without_its_country_region_and_city(page: Page, live_server, location_tree):
    """The venue alone travels, and comes back alone: the levels above it stay as the reader left them."""
    venue = location_tree["real"].pk
    page.goto(f"{live_server.url}{_LIST_URL}?{_DATES}")
    open_filter_panel(page)
    page.click("#mf-btn-4")
    page.locator("#mf-menu-4 .mf-search").fill("velo")
    with page.expect_navigation():
        page.check(f"#mf-menu-4 input[value='{venue}']")
    assert parse_qs(urlsplit(page.url).query)["location"] == [str(venue)]
    open_filter_panel(page)
    expect(page.locator("#mf-btn-4 .mf-text")).to_have_text("Velodrome")
    for level in (1, 2, 3):
        expect(page.locator(f"#mf-btn-{level} .mf-text")).to_have_class(re.compile(r"\btext-muted\b"))


@pytest.mark.django_db(transaction=True)
def test_a_citys_other_location_is_offered_under_that_city_only(page: Page, live_server, location_tree):
    """Across the whole tree one "other location" box would carry every city's catch-all at once."""
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-4")
    search = page.locator("#mf-menu-4 .mf-search")
    search.fill("Velodrome")
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['real'].pk}']")).to_have_count(1)
    search.fill("Other Venue")
    expect(page.locator("#mf-menu-4 li.mf-item-row")).to_have_count(0)

    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['city'].pk}")
    open_filter_panel(page)
    page.click("#mf-btn-4")
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['hidden'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_a_level_open_on_its_own_offers_no_box_for_all_of_it(page: Page, live_server, location_tree):
    """Every city of every country says nothing, and unticking one of them would send all the others."""
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-3")
    expect(page.locator("#mf-menu-3 li.mf-item-row").first).to_be_visible()
    expect(page.locator("#mf-menu-3 input.mf-all")).to_have_count(0)

    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['region'].pk}")
    open_filter_panel(page)
    page.click("#mf-btn-3")
    expect(page.locator("#mf-menu-3 input.mf-all")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_a_long_level_draws_a_bounded_list_and_the_search_finds_the_rest(page: Page, live_server, location_tree):
    """Venues of every city are thousands: a menu draws 200 of them and says how many more there are."""
    from locations.models import Location

    city = Location.objects.get(pk=location_tree["city"].pk)
    for n in range(210):
        city.add_child(name=f"Spot {n:03d}", name_ru=f"Spot {n:03d}", name_kk=f"Spot {n:03d}", name_en=f"Spot {n:03d}")
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
    page.click("#mf-btn-4")
    expect(page.locator("#mf-menu-4 li.mf-item-row")).to_have_count(200)
    expect(page.locator("#mf-menu-4 li.mf-more")).to_be_visible()

    page.locator("#mf-menu-4 .mf-search").fill("Spot 209")
    expect(page.locator("#mf-menu-4 li.mf-item-row")).to_have_count(1)
    expect(page.locator("#mf-menu-4 li.mf-more")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_selecting_country_auto_submits_and_populates_region(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
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
    open_filter_panel(page)
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).not_to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_multiselect_two_countries_shows_both(page: Page, live_server, kz_competition, ru_competition, location_tree):
    url = f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}&location={location_tree['ru'].pk}&{_DATES}"
    page.goto(url)
    open_filter_panel(page)
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_country_checkbox_restored_from_url(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}?location={location_tree['kz'].pk}")
    open_filter_panel(page)
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")).to_be_checked()


@pytest.mark.django_db(transaction=True)
def test_select_all_master_checkbox_selects_every_country(page: Page, live_server, location_tree):
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
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
    open_filter_panel(page)
    expect(page.locator("#mf-btn-4")).not_to_be_disabled()
    page.click("#mf-btn-4")
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['hidden'].pk}']")).to_have_count(1)
    expect(page.locator(f"#mf-menu-4 input[value='{location_tree['real'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_search_box_filters_checkboxes_case_insensitively(page: Page, live_server, location_tree):
    # The country dropdown has a type-to-filter box: typing shows only the checkboxes whose name
    # contains the text (case-insensitive); clearing it restores all.
    page.goto(f"{live_server.url}{_LIST_URL}")
    open_filter_panel(page)
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
    open_filter_panel(page)
    page.click("#mf-btn-1")
    expect(page.locator(f"#mf-menu-1 input[value='{hidden_country.pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_a_second_country_stays_ticked_after_a_region_of_the_first(
    page: Page, live_server, location_tree, kz_competition, ru_competition
):
    """The list reloads on every tick; the address keeps every ticked level, the deepest wins."""
    kz, ru, region = location_tree["kz"].pk, location_tree["ru"].pk, location_tree["region"].pk
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}{_LIST_URL}?{_DATES}")
    for menu, pk in (("#mf-menu-1", kz), ("#mf-menu-1", ru), ("#mf-menu-2", region)):
        open_filter_panel(page)
        page.click(menu.replace("menu", "btn"))
        with page.expect_navigation():
            page.check(f"{menu} input[value='{pk}']")
    expect(page.locator(f"#mf-menu-1 input[value='{ru}']")).to_be_checked()
    expect(page.locator(f"#mf-menu-2 input[value='{region}']")).to_be_checked()
    expect(page.locator("main")).to_contain_text("KZ Race")
    expect(page.locator("main")).not_to_contain_text("RU Race")
