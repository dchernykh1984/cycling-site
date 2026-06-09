"""E2E tests for the 4-level location cascade widget on submit and edit forms."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import inject_session

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _goto_submit(page: Page, live_server, user):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/calendar/submit/")


def _goto_edit(page: Page, live_server, user, competition):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/calendar/{competition.pk}/edit/")


# ---------------------------------------------------------------------------
# submit form - initial state
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_submit_form_country_dropdown_present(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    expect(page.locator("#loc-country")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_submit_form_country_dropdown_has_location_options(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    expect(page.locator(f"#loc-country option[value='{location_tree['kz'].pk}']")).to_have_count(1)
    expect(page.locator(f"#loc-country option[value='{location_tree['ru'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_submit_form_region_disabled_initially(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    expect(page.locator("#loc-region")).to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_submit_form_hidden_venue_not_shown_in_country_dropdown(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    expect(page.locator(f"#loc-country option[value='{location_tree['hidden'].pk}']")).to_have_count(0)


# ---------------------------------------------------------------------------
# submit form - cascade interaction
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_submit_form_region_populates_after_country_selection(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    page.select_option("#loc-country", str(location_tree["kz"].pk))
    expect(page.locator(f"#loc-region option[value='{location_tree['region'].pk}']")).to_have_count(1)
    expect(page.locator("#loc-region")).not_to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_submit_form_city_populates_after_region_selection(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    page.select_option("#loc-country", str(location_tree["kz"].pk))
    page.select_option("#loc-region", str(location_tree["region"].pk))
    expect(page.locator(f"#loc-city option[value='{location_tree['city'].pk}']")).to_have_count(1)
    expect(page.locator("#loc-city")).not_to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_submit_form_hidden_input_set_to_hidden_venue_on_city_selection(
    page: Page, live_server, organizer, location_tree
):
    """Selecting a city must auto-assign the hidden fallback venue to the hidden input."""
    _goto_submit(page, live_server, organizer)
    page.select_option("#loc-country", str(location_tree["kz"].pk))
    page.select_option("#loc-region", str(location_tree["region"].pk))
    page.select_option("#loc-city", str(location_tree["city"].pk))
    assert page.locator("#id_location").input_value() == str(location_tree["hidden"].pk)


@pytest.mark.django_db(transaction=True)
def test_submit_form_venue_row_appears_for_city_with_real_venues(page: Page, live_server, organizer, location_tree):
    """When a city has real (non-hidden) venues the venue row must become visible."""
    _goto_submit(page, live_server, organizer)
    page.select_option("#loc-country", str(location_tree["kz"].pk))
    page.select_option("#loc-region", str(location_tree["region"].pk))
    page.select_option("#loc-city", str(location_tree["city"].pk))
    # "Velodrome" is a real venue under Almaty
    expect(page.locator("#loc-venue-wrap")).to_be_visible()
    expect(page.locator(f"#loc-venue option[value='{location_tree['real'].pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_submit_form_selecting_real_venue_updates_hidden_input(page: Page, live_server, organizer, location_tree):
    _goto_submit(page, live_server, organizer)
    page.select_option("#loc-country", str(location_tree["kz"].pk))
    page.select_option("#loc-region", str(location_tree["region"].pk))
    page.select_option("#loc-city", str(location_tree["city"].pk))
    page.select_option("#loc-venue", str(location_tree["real"].pk))
    assert page.locator("#id_location").input_value() == str(location_tree["real"].pk)


# ---------------------------------------------------------------------------
# edit form - cascade pre-populated from existing location
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_edit_form_cascade_prepopulated_country(page: Page, live_server, organizer, location_tree):
    comp = Competition.objects.create(
        title_ru="Test Edit Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=location_tree["hidden"],
    )
    _goto_edit(page, live_server, organizer, comp)
    expect(page.locator("#loc-country")).to_have_value(str(location_tree["kz"].pk))


@pytest.mark.django_db(transaction=True)
def test_edit_form_cascade_prepopulated_region(page: Page, live_server, organizer, location_tree):
    comp = Competition.objects.create(
        title_ru="Test Edit Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=location_tree["hidden"],
    )
    _goto_edit(page, live_server, organizer, comp)
    expect(page.locator("#loc-region")).to_have_value(str(location_tree["region"].pk))


@pytest.mark.django_db(transaction=True)
def test_edit_form_cascade_prepopulated_city(page: Page, live_server, organizer, location_tree):
    comp = Competition.objects.create(
        title_ru="Test Edit Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=location_tree["hidden"],
    )
    _goto_edit(page, live_server, organizer, comp)
    expect(page.locator("#loc-city")).to_have_value(str(location_tree["city"].pk))


@pytest.mark.django_db(transaction=True)
def test_edit_form_cascade_prepopulated_real_venue(page: Page, live_server, organizer, location_tree):
    """When the saved location is a real venue the venue select shows it selected."""
    comp = Competition.objects.create(
        title_ru="Test Edit Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        location=location_tree["real"],
    )
    _goto_edit(page, live_server, organizer, comp)
    expect(page.locator("#loc-venue-wrap")).to_be_visible()
    expect(page.locator("#loc-venue")).to_have_value(str(location_tree["real"].pk))
