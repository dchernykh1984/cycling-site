"""E2E tests for proposing a venue while submitting a competition (issue #111).

After picking a city the user can open a "propose a new venue" box that includes a
mini-map: clicking the map sets the coordinates. Picking an existing venue from the
dropdown hides the box and restores the propose button.
"""

import re

import pytest
from playwright.sync_api import Page, expect

from locations.models import Location
from tests.e2e.conftest import inject_session


def _tree():
    country = Location.add_root(name="KZ", name_ru="KZ", name_kk="KZ", name_en="KZ")
    region = country.add_child(name="Region", name_ru="Region", name_kk="Region", name_en="Region")
    city = region.add_child(name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty")
    city.add_child(name="Velodrome", name_ru="Velodrome", name_kk="Velodrome", name_en="Velodrome")
    return country, region, city


def _open_city(page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/submit/")
    page.select_option("#loc-country", label="KZ")
    page.select_option("#loc-region", label="Region")
    page.select_option("#loc-city", label="Almaty")


@pytest.mark.django_db(transaction=True)
def test_propose_box_with_minimap_appears_and_sets_coords(page: Page, live_server, organizer):
    _tree()
    inject_session(page, live_server, organizer)
    _open_city(page, live_server)
    # The venue map is always visible now (issue #118) and initialised (leaflet-container).
    expect(page.locator("#venue-map")).to_have_class(re.compile(r"leaflet-container"))
    expect(page.locator("#add-venue-btn")).to_be_visible()
    page.click("#add-venue-btn")
    expect(page.locator("#new-venue-box")).to_be_visible()
    # While proposing, clicking an empty spot on the map fills the latitude/longitude fields.
    page.click("#venue-map", position={"x": 110, "y": 110})
    expect(page.locator("#new-venue-lat")).not_to_have_value("")
    expect(page.locator("#new-venue-lng")).not_to_have_value("")


@pytest.mark.django_db(transaction=True)
def test_selecting_existing_venue_hides_propose_box(page: Page, live_server, organizer):
    _tree()
    inject_session(page, live_server, organizer)
    _open_city(page, live_server)
    page.click("#add-venue-btn")
    expect(page.locator("#new-venue-box")).to_be_visible()
    page.select_option("#loc-venue", label="Velodrome")
    expect(page.locator("#new-venue-box")).to_be_hidden()
    expect(page.locator("#add-venue-btn")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_new_venue_is_named_in_each_language_and_set_aside_whole(page: Page, live_server, organizer):
    _tree()
    inject_session(page, live_server, organizer)
    _open_city(page, live_server)
    page.click("#add-venue-btn")
    names = {"#new-venue-name": "Park RU", "#new-venue-name-kk": "Park KK", "#new-venue-name-en": "Park EN"}
    for field, text in names.items():
        page.fill(field, text)
    # Picking an existing venue sets the proposal aside, every language of its name with it.
    page.select_option("#loc-venue", label="Velodrome")
    for field in names:
        expect(page.locator(field)).to_have_value("")


@pytest.mark.django_db(transaction=True)
def test_a_name_in_another_language_asks_for_the_russian_one_before_sending(page: Page, live_server, organizer):
    _tree()
    inject_session(page, live_server, organizer)
    _open_city(page, live_server)
    page.click("#add-venue-btn")
    russian = page.locator("#new-venue-name")
    expect(russian).not_to_have_attribute("required", "")
    page.fill("#new-venue-name-en", "Park EN")
    expect(russian).to_have_attribute("required", "")
    page.fill("#new-venue-name-en", "")
    expect(russian).not_to_have_attribute("required", "")
