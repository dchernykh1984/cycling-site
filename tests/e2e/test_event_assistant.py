"""E2E for the event assistant (issue #353): the event form's hooks, and the chat on the add and edit pages."""

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Discipline, DisciplineCategory
from locations.models import Location
from tests.e2e.conftest import inject_session


def _tree():
    country = Location.add_root(name_ru="Testland", name_kk="Testland", name_en="Testland")
    region = country.add_child(name_ru="Test Region", name_kk="Test Region", name_en="Test Region")
    city = region.add_child(name_ru="Testville", name_kk="Testville", name_en="Testville", lat=43.24, lng=76.89)
    city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
    shop = city.add_child(name_ru="Giant shop", name_kk="Giant shop", name_en="Giant shop", lat=43.2389, lng=76.9453)
    return city, shop


@pytest.mark.django_db(transaction=True)
def test_the_place_cascade_takes_a_venue_or_a_new_one_from_a_script(page: Page, live_server, admin_user):
    city, shop = _tree()
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.evaluate(f"window.eventLocation.select({shop.pk})")
    expect(page.locator("#loc-city")).to_have_value(str(city.pk))
    expect(page.locator("#id_location")).to_have_value(str(shop.pk))
    page.evaluate(f"window.eventLocation.propose({city.pk}, {{ru: 'Most', kk: '', en: 'Bridge'}}, 43.25, 76.95)")
    expect(page.locator("#new-venue-box")).to_be_visible()
    expect(page.locator("#new-venue-name")).to_have_value("Most")
    expect(page.locator("#new-venue-name-en")).to_have_value("Bridge")
    expect(page.locator("#new-venue-lat")).to_have_value("43.250000")
    expect(page.locator("#id_location")).to_have_value("")
    expect(page.locator("#id_new_venue_city")).to_have_value(str(city.pk))


@pytest.mark.django_db(transaction=True)
def test_the_discipline_picker_takes_its_choice_from_a_script(page: Page, live_server, admin_user):
    road = DisciplineCategory.objects.create(name_ru="Shosse", name_en="Road Test")
    gravel = Discipline.objects.create(name_ru="Grevel", name_en="Gravel Test", category=road)
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.evaluate(f"window.eventDisciplines.set([{gravel.pk}])")
    chosen = page.locator("#disciplines-hidden input[name='disciplines']")
    expect(chosen).to_have_count(1)
    expect(chosen).to_have_value(str(gravel.pk))
    expect(page.locator("#disc-dd-btn-2 .mf-text")).to_have_text("Gravel Test")
    page.evaluate("window.eventDisciplines.set([])")
    expect(chosen).to_have_count(0)
