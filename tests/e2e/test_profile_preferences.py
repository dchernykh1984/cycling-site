"""Calendar defaults in the profile, as a member sets them."""

import re

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session


def _member():
    return User.objects.create_user(
        username="e2e_prefs", email="e2e_prefs@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )


@pytest.mark.django_db(transaction=True)
def test_event_types_are_picked_from_a_dropdown_like_the_rest(page: Page, live_server, race_event_type):
    member = _member()
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/edit/")

    # The same control as directions and locations, not a row of checkboxes.
    expect(page.locator("input[type=checkbox][name=preferred_event_types]")).to_have_count(0)
    page.locator("#pe-btn-1").click()
    page.locator(f"#pe-menu-1 input.mf-item[value='{race_event_type.pk}']").check()
    page.locator("form button[type=submit].btn-primary").click()

    expect(page).to_have_url(f"{live_server.url}/ru/accounts/profile/")
    assert list(member.preferred_event_types.values_list("pk", flat=True)) == [race_event_type.pk]

    page.goto(f"{live_server.url}/ru/accounts/profile/edit/")
    expect(page.locator("#pe-btn-1")).to_contain_text("Race")


@pytest.mark.django_db(transaction=True)
def test_a_direction_is_saved_with_the_discipline_chosen_in_it(page: Page, live_server, road_category, road_discipline):
    """As the calendar's filter sends them: the ticked direction stays saved, and the discipline wins."""
    member = _member()
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/edit/")
    page.locator("#pd-btn-1").click()
    page.locator(f"#pd-menu-1 input.mf-item[value='{road_category.pk}']").check()
    page.locator("#pd-btn-2").click()
    page.locator(f"#pd-menu-2 input.mf-item[value='{road_discipline.pk}']").check()
    page.locator("form button[type=submit].btn-primary").click()

    expect(page).to_have_url(f"{live_server.url}/ru/accounts/profile/")
    assert list(member.preferred_directions.values_list("pk", flat=True)) == [road_category.pk]
    assert list(member.preferred_disciplines.values_list("pk", flat=True)) == [road_discipline.pk]


@pytest.mark.django_db(transaction=True)
def test_a_preferred_venue_is_typed_in_without_its_city_and_comes_back_alone(page: Page, live_server, location_tree):
    """The calendar's place filter: a venue is found at once, saved, and shown ticked on its own."""
    member = _member()
    venue = location_tree["real"]
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/edit/")
    page.locator("#pl-btn-4").click()
    page.locator("#pl-menu-4 .mf-search").fill("velo")
    page.locator(f"#pl-menu-4 input.mf-item[value='{venue.pk}']").check()
    page.locator("form button[type=submit].btn-primary").click()

    expect(page).to_have_url(f"{live_server.url}/ru/accounts/profile/")
    assert list(member.preferred_locations.values_list("pk", flat=True)) == [venue.pk]

    page.goto(f"{live_server.url}/ru/accounts/profile/edit/")
    expect(page.locator("#pl-btn-4")).to_contain_text("Velodrome")
    expect(page.locator("#pl-btn-3 .mf-text")).to_have_class(re.compile(r"\btext-muted\b"))
