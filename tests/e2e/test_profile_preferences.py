"""Calendar defaults in the profile, as a member sets them."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session


@pytest.mark.django_db(transaction=True)
def test_event_types_are_picked_from_a_dropdown_like_the_rest(page: Page, live_server, race_event_type):
    member = User.objects.create_user(
        username="e2e_prefs", email="e2e_prefs@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
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
