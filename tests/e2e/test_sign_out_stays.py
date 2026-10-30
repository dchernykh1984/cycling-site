"""Signing out from the header keeps the reader on the page they were on, in the skin they had.

It sent them to the home page, drawn in the default skin rather than the member's own.
"""

import pytest
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import E2E_SKIN, UPCOMING, inject_session


@pytest.mark.django_db(transaction=True)
def test_signing_out_from_the_header_stays_on_the_event_in_the_member_s_skin(page: Page, live_server):
    from accounts.models import User

    # Not the suite's skin, which a guest without a cookie gets anyway.
    theme = "light" if E2E_SKIN == "dark" else "dark"
    user = User.objects.create_user(
        username="e2e_leaving", email="e2e_leaving@test.local", password="testpass123!", theme=theme
    )
    event = Competition.objects.create(
        title_ru="E2E sign-out race", date_start=UPCOMING, status=Competition.Status.APPROVED
    )
    with translation_override("ru"):
        log_out, log_in = gettext("Log out"), gettext("Log in")
    inject_session(page, live_server, user)
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server.url}/ru/calendar/{event.pk}/")
    page.locator(".dropdown-toggle", has_text=user.email).click()
    page.get_by_role("button", name=log_out, exact=True).click()
    expect(page.locator("header, nav").get_by_role("link", name=log_in, exact=True).first).to_be_visible()
    expect(page).to_have_url(f"{live_server.url}/ru/calendar/{event.pk}/")
    expect(page.locator("html")).to_have_attribute("data-skin", theme)
