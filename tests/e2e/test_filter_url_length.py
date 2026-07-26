"""E2E regression: a wide filter selection must not build a request line the server refuses.

Selecting every country and region and then switching to the list view produced one ``&location=``
parameter per selected id -- 7091 bytes of request line against the ~4 KB the server accepts, which
it answered with a bare "Bad Request: Request Line is too large (7091 > 4094)" before any view ran.

Two things keep the query string short now, and both are pinned here: ids travel as one
comma-joined value per filter, and a lower level whose every option is ticked is dropped in favour
of its parent level, which selects the same events far more briefly. The top level is kept even
when whole -- sending nothing would also admit competitions with no location at all.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, expect

_LIST_URL = "/calendar/list/"
_DATES = "date_from=2026-07-01&date_to=2026-07-31"


def _query(url: str) -> dict:
    return parse_qs(urlsplit(url).query)


def _href(page: Page, link_id: str) -> str:
    href = page.locator(link_id).get_attribute("href")
    assert href is not None, f"{link_id} has no href"
    return href


def _switcher_query(page: Page, link_id: str) -> dict:
    return _query(_href(page, link_id))


@pytest.fixture
def wide_tree(location_tree):
    """The shared tree plus a third country, so a level can be selected in part as well as whole."""
    from locations.models import Location

    third = Location.add_root(name="BY", name_ru="BY", name_kk="BY", name_en="BY", sort_order=3)
    return {**location_tree, "by": Location.objects.get(pk=third.pk)}


@pytest.mark.django_db(transaction=True)
def test_selecting_every_country_and_region_stays_within_the_request_line(page: Page, live_server, wide_tree):
    """The reported selection: every country *and* every region ticked, on the full country list.

    The top level is kept even when whole -- dropping it would also admit competitions with no
    location at all -- so what has to keep the link short is the two other rules: the regions
    collapse back onto the countries, and the ids travel as one comma-joined value.
    """
    page.goto(f"{live_server.url}/calendar/?{_DATES}")
    page.click("#mf-btn-1")
    page.click("#mf-menu-1 input.mf-all")
    expect(page.locator("#mf-btn-2")).to_be_enabled()
    page.click("#mf-btn-2")
    page.click("#mf-menu-2 input.mf-all")

    href = _href(page, "#view-link-list")
    assert len(href) < 4094, len(href)
    location = _query(href)["location"]
    assert len(location) == 1, location  # one value, not one parameter per country
    selected = set(location[0].split(","))
    assert {str(wide_tree[k].pk) for k in ("kz", "ru", "by")} <= selected


@pytest.mark.django_db(transaction=True)
def test_two_of_three_countries_travel_as_one_comma_joined_parameter(page: Page, live_server, wide_tree):
    """A partial selection is still sent -- as a single value, not one parameter per id."""
    kz, ru = wide_tree["kz"].pk, wide_tree["ru"].pk
    page.goto(f"{live_server.url}/calendar/?{_DATES}")
    page.click("#mf-btn-1")
    page.click(f"#mf-menu-1 input[value='{kz}']")
    page.click(f"#mf-menu-1 input[value='{ru}']")

    location = _switcher_query(page, "#view-link-list")["location"]
    assert location == [f"{kz},{ru}"], location


@pytest.mark.django_db(transaction=True)
def test_selecting_every_region_of_a_country_falls_back_to_that_country(page: Page, live_server, wide_tree):
    """A whole lower level is dropped for its parent, which selects the same events far more briefly."""
    kz = wide_tree["kz"].pk
    page.goto(f"{live_server.url}/calendar/?{_DATES}")
    page.click("#mf-btn-1")
    page.click(f"#mf-menu-1 input[value='{kz}']")
    page.click("#mf-btn-2")
    page.click("#mf-menu-2 input.mf-all")

    assert _switcher_query(page, "#view-link-list")["location"] == [str(kz)]


@pytest.mark.django_db(transaction=True)
def test_the_list_page_survives_switching_with_everything_selected(
    page: Page, live_server, wide_tree, kz_competition, ru_competition
):
    """The reported failure end to end: select everything, switch to the list, get the list."""
    page.goto(f"{live_server.url}/calendar/?{_DATES}")
    page.click("#mf-btn-1")
    page.click("#mf-menu-1 input.mf-all")
    page.click("#mf-btn-1")  # close the dropdown before clicking the switcher underneath
    with page.expect_navigation():
        page.click("#view-link-list")

    assert len(page.url) < 4094
    expect(page.locator("body")).not_to_contain_text("Bad Request")
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).to_contain_text("RU Race")


@pytest.mark.django_db(transaction=True)
def test_the_list_form_submits_one_input_per_filter(page: Page, live_server, wide_tree, kz_competition):
    """The list's own filter form is GET too, so its hidden inputs must be joined the same way."""
    kz, ru = wide_tree["kz"].pk, wide_tree["ru"].pk
    # Each tick auto-submits the form, so the second one is picked after the reload.
    page.goto(f"{live_server.url}{_LIST_URL}?{_DATES}")
    page.click("#mf-btn-1")
    with page.expect_navigation():
        page.click(f"#mf-menu-1 input[value='{kz}']")
    page.click("#mf-btn-1")
    with page.expect_navigation():
        page.click(f"#mf-menu-1 input[value='{ru}']")

    assert _query(page.url)["location"] == [f"{kz},{ru}"]
    expect(page.locator("body")).to_contain_text("KZ Race")


@pytest.mark.django_db(transaction=True)
def test_a_comma_joined_location_filters_the_same_as_separate_parameters(
    page: Page, live_server, wide_tree, kz_competition, ru_competition
):
    """The compact form must mean what the old one meant -- the server contract the JS relies on."""
    kz = wide_tree["kz"].pk
    by = wide_tree["by"].pk
    page.goto(f"{live_server.url}{_LIST_URL}?location={kz},{by}&{_DATES}")
    expect(page.locator("body")).to_contain_text("KZ Race")
    expect(page.locator("body")).not_to_contain_text("RU Race")
