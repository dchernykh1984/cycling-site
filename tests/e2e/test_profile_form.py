"""The profile form names each field by its label: a screen reader says it, a tap on the words reaches it."""

import pytest
from django.utils.translation import gettext, override
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session

FIELDS = (
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("birth_date", "Date of birth"),
    ("team", "Team"),
    ("city", "City"),
    ("strava_link", "Strava link"),
    ("sports_achievements", "Sports achievements"),
)


@pytest.mark.django_db(transaction=True)
def test_every_field_of_the_profile_form_is_named_by_its_label(page: Page, live_server):
    member = User.objects.create_user(
        username="e2e_form", email="e2e_form@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/edit/")
    with override("ru"):
        labels = {name: gettext(label) for name, label in FIELDS}
        gender = gettext("Gender")
    for name, label in labels.items():
        expect(page.get_by_label(label, exact=True)).to_have_attribute("name", name)
    expect(page.get_by_role("radiogroup", name=gender)).to_be_visible()
    page.locator("main form").get_by_text(labels["last_name"], exact=True).click()
    expect(page.locator("input[name=last_name]")).to_be_focused()
