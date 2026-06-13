"""E2E tests for the locations map page and location management UI."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import inject_session

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _map_url(live_server):
    from locations.models import LocationsMapPage

    page = LocationsMapPage.objects.live().first()
    if page:
        return f"{live_server.url}{page.url}"
    return f"{live_server.url}/map/"


@pytest.fixture
def map_page(db, wagtail_home_page):
    from wagtail.models import Locale, Page

    from home.models import HomePage
    from locations.models import LocationsMapPage

    if LocationsMapPage.objects.exists():
        return LocationsMapPage.objects.first()

    locale = Locale.objects.get(language_code="ru")
    home = HomePage.objects.filter(locale=locale, depth=2).first()
    if home is None:
        home = Page.objects.filter(depth=2).first()
    instance = LocationsMapPage(title="Map", slug="map", live=True, locale=locale)
    home.add_child(instance=instance)
    return instance


@pytest.fixture
def location_with_coords(db):
    from locations.models import Location

    return Location.add_root(
        name="Almaty",
        name_ru="Almaty",
        name_kk="Almaty",
        name_en="Almaty",
        lat="43.238949",
        lng="76.889709",
    )


# ---------------------------------------------------------------------------
# map page visibility
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_map_page_renders_for_anonymous(page: Page, live_server, map_page):
    page.goto(_map_url(live_server))
    expect(page.locator("#locations-map")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_map_page_no_add_button_for_anonymous(page: Page, live_server, map_page):
    page.goto(_map_url(live_server))
    expect(page.locator("a[href='/locations/add/']")).not_to_be_attached()


@pytest.mark.django_db(transaction=True)
def test_map_page_add_button_visible_for_admin(page: Page, live_server, map_page, admin_user):
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    expect(page.locator("a[href='/locations/add/']")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_map_page_manage_table_visible_for_admin(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    expect(page.locator("table")).to_be_visible()


# ---------------------------------------------------------------------------
# add location form
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_add_form_accessible_for_admin(page: Page, live_server, map_page, admin_user):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/add/")
    expect(page.locator("#id_name_ru")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_add_form_forbidden_for_participant(page: Page, live_server, map_page, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/locations/add/")
    expect(page.locator("body")).to_contain_text("403")


@pytest.mark.django_db(transaction=True)
def test_admin_can_create_location(page: Page, live_server, map_page, admin_user):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/add/")
    page.fill("#id_name_ru", "Test City")
    page.locator("#location-form button[type=submit]").click()
    page.wait_for_load_state("networkidle")

    from locations.models import Location

    assert Location.objects.filter(name_ru="Test City").exists()


# ---------------------------------------------------------------------------
# edit location form
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_form_accessible_for_admin(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/{location_with_coords.pk}/edit/")
    expect(page.locator("#id_name_ru")).to_have_value("Almaty")


@pytest.mark.django_db(transaction=True)
def test_admin_can_edit_location(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/{location_with_coords.pk}/edit/")
    page.fill("#id_name_ru", "Renamed City")
    page.locator("#location-form button[type=submit]").click()
    page.wait_for_load_state("networkidle")

    location_with_coords.refresh_from_db()
    assert location_with_coords.name_ru == "Renamed City"


# ---------------------------------------------------------------------------
# edit button present in management table
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_manage_table_has_edit_button(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    edit_link = page.locator(f"a[href='/locations/{location_with_coords.pk}/edit/']")
    expect(edit_link).to_be_visible()
