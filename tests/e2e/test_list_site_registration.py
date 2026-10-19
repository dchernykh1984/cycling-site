"""The events list offers registration that runs on this site.

The links cell only ever read the external registration URL, so an event taking entries here showed
an empty cell -- on a phone, an event card with no way to sign up from it.
"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import AROUND_UPCOMING


@pytest.mark.django_db(transaction=True)
def test_list_row_offers_registration_open_on_this_site(page: Page, live_server, competition_with_approval):
    page.goto(f"{live_server.url}/ru/calendar/list/?{AROUND_UPCOMING}")
    row = page.locator("tr", has_text="E2E Approval Race RU")
    register = row.locator(f'a[href="/ru/competitions/{competition_with_approval.pk}/register/"]')
    expect(register).to_be_visible()
    register.click()
    # An anonymous reader is sent to sign in first, with the form as the place to come back to.
    expect(page).to_have_url(re.compile(rf"competitions/{competition_with_approval.pk}/register/"))
