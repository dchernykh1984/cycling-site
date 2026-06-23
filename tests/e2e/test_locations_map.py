"""E2E tests for the locations map page and location management UI."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import inject_session, switch_locale

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
def location_tree_basic(db):
    """Minimal country -> region -> city tree for form tests."""
    from locations.models import Location

    country = Location.add_root(name="KZ", name_ru="KZ", name_kk="KZ", name_en="KZ")
    region = country.add_child(
        name="Almaty Region", name_ru="Almaty Region", name_kk="Almaty Region", name_en="Almaty Region"
    )
    city = region.add_child(name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty")
    return {"country": country, "region": region, "city": city}


@pytest.fixture
def location_with_coords(db, location_tree_basic):

    city = location_tree_basic["city"]
    return city.add_child(
        name="Velodrome",
        name_ru="Velodrome",
        name_kk="Velodrome",
        name_en="Velodrome",
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
def test_add_form_accessible_for_non_admin(page: Page, live_server, map_page, organizer):
    # Issue #111: any registered user may open the location form (to propose); not 403.
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/locations/add/")
    expect(page.locator("#id_name_ru")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("403")


@pytest.mark.django_db(transaction=True)
def test_admin_can_create_location(page: Page, live_server, map_page, admin_user, location_tree_basic):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/add/")

    country = location_tree_basic["country"]
    region = location_tree_basic["region"]
    city = location_tree_basic["city"]

    # Each cascade level is rebuilt by the previous level's change handler, so wait for the
    # dependent select to become enabled before selecting in it (avoids a CI race).
    page.select_option("#loc-country", str(country.pk))
    expect(page.locator("#loc-region")).to_be_enabled()
    page.select_option("#loc-region", str(region.pk))
    expect(page.locator("#loc-city")).to_be_enabled()
    page.select_option("#loc-city", str(city.pk))
    # The deepest selection is mirrored into the hidden parent field; wait for it before submit.
    expect(page.locator("#id_parent")).to_have_value(str(city.pk))
    page.fill("#id_name_ru", "Test Venue")
    page.locator("#location-form button[type=submit]").click()
    page.wait_for_url(lambda url: "/locations/add/" not in url)

    from locations.models import Location

    venue = Location.objects.get(name_ru="Test Venue")
    assert venue.depth == 4
    assert venue.get_parent().pk == city.pk


# ---------------------------------------------------------------------------
# edit location form
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_form_accessible_for_admin(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/{location_with_coords.pk}/edit/")
    expect(page.locator("#id_name_ru")).to_have_value("Velodrome")


@pytest.mark.django_db(transaction=True)
def test_admin_can_edit_location(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/{location_with_coords.pk}/edit/")
    page.fill("#id_name_ru", "Renamed Venue")
    page.locator("#location-form button[type=submit]").click()
    # Wait for the post-save redirect (networkidle can settle before the POST round-trips on CI).
    page.wait_for_url(lambda url: "/edit/" not in url)

    location_with_coords.refresh_from_db()
    assert location_with_coords.name_ru == "Renamed Venue"


# ---------------------------------------------------------------------------
# edit button present in management table
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_manage_table_has_edit_button(page: Page, live_server, map_page, admin_user, location_with_coords):
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    # The edit link carries a ?next= return target, so match by prefix.
    edit_link = page.locator(f"a[href^='/locations/{location_with_coords.pk}/edit/']")
    expect(edit_link).to_be_visible()


# ---------------------------------------------------------------------------
# admin creates structural nodes (cascade JS drives the hidden parent)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_admin_can_create_country(page: Page, live_server, map_page, admin_user):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/add/")
    # No cascade selection -> empty parent -> a depth-1 country.
    expect(page.locator("#id_parent")).to_have_value("")
    page.fill("#id_name_ru", "Newland")
    page.locator("#location-form button[type=submit]").click()
    page.wait_for_url(lambda url: "/locations/add/" not in url)

    from locations.models import Location

    country = Location.objects.get(name_ru="Newland")
    assert country.depth == 1
    assert country.get_parent() is None


@pytest.mark.django_db(transaction=True)
def test_admin_can_create_region_under_country(page: Page, live_server, map_page, admin_user, location_tree_basic):
    country = location_tree_basic["country"]
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/add/")
    page.select_option("#loc-country", str(country.pk))
    # Selecting only the country makes it the parent -> the new node is a depth-2 region.
    expect(page.locator("#id_parent")).to_have_value(str(country.pk))
    page.fill("#id_name_ru", "Brand New Region")
    page.locator("#location-form button[type=submit]").click()
    page.wait_for_url(lambda url: "/locations/add/" not in url)

    from locations.models import Location

    region = Location.objects.get(name_ru="Brand New Region")
    assert region.depth == 2
    assert region.get_parent().pk == country.pk


@pytest.mark.django_db(transaction=True)
def test_create_hint_for_organizer_is_venue_only(page: Page, live_server, map_page, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/locations/add/")
    switch_locale(page, "en")  # the hint is localized; check the English source text
    expect(page.locator("#location-form")).to_contain_text("venue inside the chosen city")


@pytest.mark.django_db(transaction=True)
def test_create_hint_for_admin_is_not_venue_only(page: Page, live_server, map_page, admin_user):
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/add/")
    switch_locale(page, "en")
    expect(page.locator("#location-form")).not_to_contain_text("venue inside the chosen city")


# ---------------------------------------------------------------------------
# edit form prefill (cascade parent chain + coordinates)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_prefills_parent_cascade_and_coords(
    page: Page, live_server, map_page, admin_user, location_tree_basic, location_with_coords
):
    country = location_tree_basic["country"]
    region = location_tree_basic["region"]
    city = location_tree_basic["city"]
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/{location_with_coords.pk}/edit/")
    expect(page.locator("#loc-country")).to_have_value(str(country.pk))
    expect(page.locator("#loc-region")).to_have_value(str(region.pk))
    expect(page.locator("#loc-city")).to_have_value(str(city.pk))
    expect(page.locator("#id_parent")).to_have_value(str(city.pk))
    expect(page.locator("#id_lat")).to_have_value("43.238949")
    expect(page.locator("#id_lng")).to_have_value("76.889709")


@pytest.mark.django_db(transaction=True)
def test_edit_preserves_hidden_parent_on_plain_save(page: Page, live_server, map_page, admin_user, location_tree_basic):
    from locations.models import Location

    country = location_tree_basic["country"]
    region = location_tree_basic["region"]
    hidden_city = region.add_child(name="Hidden City", name_ru="Hidden City", is_hidden=True)
    venue = hidden_city.add_child(name="Hidden Child Venue", name_ru="Hidden Child Venue")

    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/locations/{venue.pk}/edit/")

    expect(page.locator("#loc-country")).to_have_value(str(country.pk))
    expect(page.locator("#loc-region")).to_have_value(str(region.pk))
    expect(page.locator("#loc-city")).to_have_value(str(hidden_city.pk))
    expect(page.locator("#id_parent")).to_have_value(str(hidden_city.pk))

    page.fill("#id_name_ru", "Hidden Child Venue Renamed")
    page.locator("#location-form button[type=submit]").click()
    page.wait_for_url(lambda url: f"/locations/{venue.pk}/edit/" not in url)

    venue = Location.objects.get(pk=venue.pk)
    assert venue.name_ru == "Hidden Child Venue Renamed"
    assert venue.depth == 4
    assert venue.get_parent().pk == hidden_city.pk


# ---------------------------------------------------------------------------
# map-page filter, pager and action return targets
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_map_filter_renders_country_options(page: Page, live_server, map_page, admin_user, location_tree):
    # The map-page filter is the shared multi-select partial (its selection JS is covered by
    # test_location_filter.py); here we just confirm the cascade is wired with the page's data.
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    page.click("#mf-btn-1", force=True)
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['kz'].pk}']")).to_have_count(1)
    expect(page.locator(f"#mf-menu-1 input[value='{location_tree['ru'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_map_filter_checkbox_narrows_table(page: Page, live_server, map_page, admin_user, location_tree):
    # Real JS workflow: ticking a country checkbox runs onCalendarFilterChange -> sync -> submit,
    # which narrows the URL, the management table and the map markers to that subtree.
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    page.click("#mf-btn-1", force=True)  # open the country dropdown (past the sticky navbar)
    with page.expect_navigation():
        # Click the menu item label, which ticks the checkbox and auto-submits the form.
        page.locator(f"#mf-menu-1 label:has(input[value='{location_tree['kz'].pk}'])").click()
    assert f"location={location_tree['kz'].pk}" in page.url
    table = page.locator("table")
    expect(table).to_contain_text("KZ Region")
    expect(table).not_to_contain_text("RU Region")


@pytest.mark.django_db(transaction=True)
def test_marker_popup_edit_link_navigates(page: Page, live_server, map_page, admin_user, location_with_coords):
    # Clicking a filtered map marker opens its popup; Edit navigates to the form and saving returns
    # to the same map filter/page rather than resetting the management view.
    inject_session(page, live_server, admin_user)
    page.goto(f"{_map_url(live_server)}?location={location_with_coords.pk}&page=1")
    marker = page.locator(".leaflet-marker-icon").first
    expect(marker).to_be_visible()
    marker.click()
    edit_link = page.locator(f".leaflet-popup a[href^='/locations/{location_with_coords.pk}/edit/']")
    expect(edit_link).to_be_visible()
    with page.expect_navigation():
        edit_link.click()
    assert f"/locations/{location_with_coords.pk}/edit/" in page.url
    expect(page.locator("#id_name_ru")).to_have_value("Velodrome")
    with page.expect_navigation():
        page.locator("#location-form button[type='submit']").click()
    assert f"location={location_with_coords.pk}" in page.url
    assert "page=1" in page.url


@pytest.mark.django_db(transaction=True)
def test_pager_jump_to_arbitrary_page(page: Page, live_server, map_page, admin_user):
    from locations.models import Location

    for i in range(25):
        Location.add_root(name=f"P{i:02d}", name_ru=f"P{i:02d}", name_en=f"P{i:02d}")
    inject_session(page, live_server, admin_user)
    page.goto(_map_url(live_server))
    page.fill("input[name='page']", "2")
    with page.expect_navigation():
        page.locator("input[name='page']").press("Enter")
    assert "page=2" in page.url


@pytest.mark.django_db(transaction=True)
def test_hide_action_preserves_active_filter(page: Page, live_server, map_page, admin_user, location_tree):
    inject_session(page, live_server, admin_user)
    page.goto(f"{_map_url(live_server)}?location={location_tree['kz'].pk}")
    with page.expect_navigation():
        page.locator("form[action*='/hide/'] button[type=submit]").first.click()
    # The hide action returns to the same filtered page rather than the first unfiltered one.
    assert f"location={location_tree['kz'].pk}" in page.url
