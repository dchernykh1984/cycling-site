"""E2E tests for the event form's place picker: country, region, city and venue, one of each.

Each level is a searchable menu. Any level can be searched before the ones above it; picking a place
fills in every level above it, and a level lists only what lies under the nearest level picked above.
"""

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import UPCOMING, choose_place, inject_session, place_rows

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _goto_submit(page: Page, live_server, user):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/ru/calendar/submit/")


def _goto_edit(page: Page, live_server, user, competition):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/ru/calendar/{competition.pk}/edit/")


def _found(page: Page, level: str, query: str) -> list[str]:
    """The rows a level's menu shows for what is typed into its search box."""
    page.locator(f"#loc-{level}").click()
    page.locator(f"#loc-{level}-menu .loc-pick-search").fill(query)
    rows = page.locator(f"#loc-{level}-menu .loc-pick-row .dropdown-item").all_inner_texts()
    page.keyboard.press("Escape")
    return rows


def _picked(page: Page, level: str, place) -> None:
    expect(page.locator(f"#loc-{level}")).to_have_attribute("data-value", str(place.pk))


def _event_at(place, organizer) -> Competition:
    return Competition.objects.create(
        title_ru="Test Edit Race",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=place,
    )


# ---------------------------------------------------------------------------
# submit form - what each level lists
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_every_level_opens_and_lists_its_whole_depth_before_anything_is_picked(
    page: Page, live_server, organizer, location_tree
):
    _goto_submit(page, live_server, organizer)
    # The migrations' own places are listed too, a level of hundreds drawn up to its first rows: the
    # fixture's places are found by searching, as a person finds them.
    assert {"KZ", "RU"} <= set(place_rows(page, "country"))
    assert "KZ Region" in _found(page, "region", "kz region")
    assert "RU Region" in _found(page, "region", "ru region")
    assert "Almaty" in _found(page, "city", "almaty")
    assert "Moscow" in _found(page, "city", "moscow")
    # A city's catch-all means something only under its own city, so a venue search across the whole
    # tree leaves it out.
    assert _found(page, "venue", "velodrome") == ["Velodrome"]
    assert _found(page, "venue", "other venue") == []


@pytest.mark.django_db(transaction=True)
def test_a_level_lists_only_what_lies_under_the_level_picked_above_it(
    page: Page, live_server, organizer, location_tree
):
    moscow = location_tree["ru_hidden"].get_parent()
    moscow.add_child(name="Luzhniki", name_ru="Luzhniki", name_kk="Luzhniki", name_en="Luzhniki")
    _goto_submit(page, live_server, organizer)
    choose_place(page, "country", "RU")
    assert place_rows(page, "region") == ["RU Region"]
    assert place_rows(page, "city") == ["Moscow"]
    assert place_rows(page, "venue") == ["Luzhniki"]


@pytest.mark.django_db(transaction=True)
def test_a_picked_city_lists_its_venues_and_its_catch_all(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "city", "Almaty")
    assert place_rows(page, "venue") == ["Velodrome", "Other Venue"]


# ---------------------------------------------------------------------------
# submit form - picking fills in the levels above
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_a_venue_found_straight_away_fills_in_its_city_region_and_country(
    page: Page, live_server, organizer, location_tree
):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "venue", "Velodrome")
    _picked(page, "country", location_tree["kz"])
    _picked(page, "region", location_tree["region"])
    _picked(page, "city", location_tree["city"])
    _picked(page, "venue", location_tree["real"])
    assert page.locator("#id_location").input_value() == str(location_tree["real"].pk)


@pytest.mark.django_db(transaction=True)
def test_a_city_found_straight_away_fills_in_its_region_and_country_and_stands_for_its_catch_all(
    page: Page, live_server, organizer, location_tree
):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "city", "Almaty")
    _picked(page, "country", location_tree["kz"])
    _picked(page, "region", location_tree["region"])
    _picked(page, "venue", location_tree["hidden"])
    expect(page.locator("#loc-venue")).to_have_text("Other Venue")
    assert page.locator("#id_location").input_value() == str(location_tree["hidden"].pk)


@pytest.mark.django_db(transaction=True)
def test_a_place_elsewhere_replaces_the_levels_above_and_drops_a_venue_not_under_it(
    page: Page, live_server, organizer, location_tree
):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "venue", "Velodrome")
    choose_place(page, "country", "RU")
    _picked(page, "country", location_tree["ru"])
    for level in ("region", "city", "venue"):
        expect(page.locator(f"#loc-{level}")).to_have_attribute("data-value", "")
    choose_place(page, "city", "Moscow")
    _picked(page, "venue", location_tree["ru_hidden"])
    assert page.locator("#id_location").input_value() == str(location_tree["ru_hidden"].pk)


@pytest.mark.django_db(transaction=True)
def test_picking_the_same_country_again_keeps_what_was_picked_under_it(
    page: Page, live_server, organizer, location_tree
):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "venue", "Velodrome")
    choose_place(page, "country", "KZ")
    _picked(page, "venue", location_tree["real"])


@pytest.mark.django_db(transaction=True)
def test_unpicking_a_venue_leaves_its_city_s_catch_all(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "venue", "Velodrome")
    page.locator("#loc-venue").click()
    page.locator("#loc-venue-menu .loc-pick-clear").click()
    _picked(page, "city", location_tree["city"])
    _picked(page, "venue", location_tree["hidden"])
    assert page.locator("#id_location").input_value() == str(location_tree["hidden"].pk)


@pytest.mark.django_db(transaction=True)
def test_unpicking_the_country_clears_every_level(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    choose_place(page, "venue", "Velodrome")
    page.locator("#loc-country").click()
    page.locator("#loc-country-menu .loc-pick-clear").click()
    for level in ("country", "region", "city", "venue"):
        expect(page.locator(f"#loc-{level}")).to_have_attribute("data-value", "")
    assert page.locator("#id_location").input_value() == ""


# The site's own catch-alls under every region and country, as the migrations name them: a region
# or a country picked alone stands for the catch-all of its "other city".
OTHER_CITY = "\u0414\u0440\u0443\u0433\u043e\u0439 \u0433\u043e\u0440\u043e\u0434"
OTHER_REGION = "\u0414\u0440\u0443\u0433\u043e\u0439 \u0440\u0435\u0433\u0438\u043e\u043d"


def _catch_all(parent, city_name):
    city = parent.add_child(name=city_name, name_ru=city_name, is_hidden=True)
    return city.add_child(name="Other Venue", name_ru="Other Venue", is_hidden=True)


@pytest.mark.django_db(transaction=True)
def test_a_region_or_a_country_picked_alone_stands_for_its_other_city(
    page: Page, live_server, organizer, location_tree
):
    region_catch_all = _catch_all(location_tree["region"], OTHER_CITY)
    other_region = location_tree["kz"].add_child(name=OTHER_REGION, name_ru=OTHER_REGION, is_hidden=True)
    country_catch_all = _catch_all(other_region, OTHER_CITY)
    _goto_submit(page, live_server, organizer)
    choose_place(page, "region", "KZ Region")
    assert page.locator("#id_location").input_value() == str(region_catch_all.pk)
    choose_place(page, "country", "RU")
    choose_place(page, "country", "KZ")
    assert page.locator("#id_location").input_value() == str(country_catch_all.pk)


@pytest.mark.django_db(transaction=True)
def test_enter_picks_the_first_place_found(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    page.locator("#loc-city").click()
    search = page.locator("#loc-city-menu .loc-pick-search")
    expect(search).to_be_focused()
    search.fill("mosc")
    search.press("Enter")
    _picked(page, "city", location_tree["ru_hidden"].get_parent())
    expect(page.locator("#loc-city-menu")).to_be_hidden()
    assert page.url.endswith("/ru/calendar/submit/")  # the form was not sent


@pytest.mark.django_db(transaction=True)
def test_hidden_venue_not_listed_among_countries(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    assert "Other Venue" not in place_rows(page, "country")


# ---------------------------------------------------------------------------
# edit form - the picker shows the saved place
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_form_shows_a_city_s_catch_all_with_everything_above_it(page: Page, live_server, organizer, location_tree):
    _goto_edit(page, live_server, organizer, _event_at(location_tree["hidden"], organizer))
    _picked(page, "country", location_tree["kz"])
    _picked(page, "region", location_tree["region"])
    _picked(page, "city", location_tree["city"])
    _picked(page, "venue", location_tree["hidden"])


@pytest.mark.django_db(transaction=True)
def test_edit_form_shows_the_saved_venue(page: Page, live_server, organizer, location_tree):
    _goto_edit(page, live_server, organizer, _event_at(location_tree["real"], organizer))
    _picked(page, "venue", location_tree["real"])
    expect(page.locator("#loc-venue")).to_have_text("Velodrome")
    assert page.locator("#id_location").input_value() == str(location_tree["real"].pk)


# ---------------------------------------------------------------------------
# issue #118 - existing venues shown on the maps; click a marker to select one
# ---------------------------------------------------------------------------


def _venue_with_coords(location_tree):
    real = location_tree["real"]
    real.lat = "43.230000"
    real.lng = "76.940000"
    real.save(update_fields=["lat", "lng"])
    return real


@pytest.mark.django_db(transaction=True)
def test_add_location_page_shows_existing_venue_markers(page: Page, live_server, organizer, location_tree):
    _venue_with_coords(location_tree)
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/locations/add/")
    expect(page.locator("#coord-picker path.leaflet-interactive")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_submit_form_shows_existing_venue_markers(page: Page, live_server, organizer, location_tree):
    _venue_with_coords(location_tree)
    _goto_submit(page, live_server, organizer)
    expect(page.locator("#venue-map path.leaflet-interactive")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_submit_form_clicking_marker_selects_venue_and_hides_propose(page: Page, live_server, organizer, location_tree):
    real = _venue_with_coords(location_tree)
    _goto_submit(page, live_server, organizer)
    choose_place(page, "city", "Almaty")
    page.click("#add-venue-btn")
    expect(page.locator("#new-venue-box")).to_be_visible()
    assert page.locator("#id_location").input_value() == ""
    page.locator("#venue-map path.leaflet-interactive").first.click()
    assert page.locator("#id_location").input_value() == str(real.pk)
    _picked(page, "venue", real)
    _picked(page, "country", location_tree["kz"])
    expect(page.locator("#new-venue-box")).not_to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_submit_form_hidden_city_is_selectable(page: Page, live_server, organizer, location_tree):
    # Issue #113: a hidden real city must stay selectable when creating a competition.
    hidden_city = location_tree["region"].add_child(
        name="HiddenCity", name_ru="HiddenCity", name_kk="HiddenCity", name_en="HiddenCity", is_hidden=True
    )
    _goto_submit(page, live_server, organizer)
    choose_place(page, "city", "HiddenCity")
    _picked(page, "city", hidden_city)
    _picked(page, "region", location_tree["region"])
