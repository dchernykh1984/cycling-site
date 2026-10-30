"""Signing in from the header brings the reader back to the page they were on.

It brought them to the home page, so a reader who opened an event from a chat and signed in to
enter the race had to find the race again.
"""

import pytest
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import UPCOMING


@pytest.mark.django_db(transaction=True)
def test_signing_in_from_the_header_returns_to_the_event(page: Page, live_server):
    from allauth.account.models import EmailAddress

    from accounts.models import User

    user = User.objects.create_user(
        username="e2e_back", email="e2e_back@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    event = Competition.objects.create(
        title_ru="E2E sign-in race", date_start=UPCOMING, status=Competition.Status.APPROVED
    )
    with translation_override("ru"):
        log_in = gettext("Log in")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server.url}/ru/calendar/{event.pk}/")
    page.locator("header, nav").get_by_role("link", name=log_in, exact=True).first.click()
    page.locator("input[name='login']").fill(user.email)
    page.locator("input[name='password']").fill("testpass123!")
    page.locator("form button[type='submit']").last.click()
    expect(page).to_have_url(f"{live_server.url}/ru/calendar/{event.pk}/")
