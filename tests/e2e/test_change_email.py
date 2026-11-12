"""A member changes the address they sign in with from the profile; the new one waits for its confirmation."""

import pytest
from allauth.account.models import EmailAddress
from django.utils.translation import gettext, override
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session


@pytest.mark.django_db(transaction=True)
def test_a_member_asks_for_a_new_address_from_the_profile(page: Page, live_server):
    member = User.objects.create_user(
        username="e2e_mover", email="old@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    EmailAddress.objects.create(user=member, email="old@test.local", verified=True, primary=True)
    inject_session(page, live_server, member)
    with override("ru"):
        change, field, send = gettext("Change email"), gettext("Change to"), gettext("Change Email")
        waiting = gettext("Your email address is still pending verification.")
    page.goto(f"{live_server.url}/ru/accounts/profile/")
    page.get_by_role("link", name=change, exact=True).click()
    page.get_by_label(field).fill("new@test.local")
    page.get_by_role("button", name=send, exact=True).click()
    expect(page.get_by_text(waiting)).to_be_visible()
    expect(page.locator("#new_email")).to_have_value("new@test.local")
    member.refresh_from_db()
    assert member.email == "old@test.local"
