"""E2E tests for the competition list filter auto-submit behaviour."""

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db(transaction=True)
def test_filter_form_has_no_apply_button(page: Page, live_server):
    """The 'Apply' button was removed; filters submit on change instead."""
    page.goto(f"{live_server.url}/calendar/list/")
    # There should be a Reset link but no submit/apply button inside the filter form
    filter_form = page.locator("#filter-form")
    expect(filter_form).to_be_visible()
    expect(filter_form.locator("button[type=submit]")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_date_filter_auto_submits(page: Page, live_server, approved_competition):
    """Changing the date_from input auto-submits and reflects the new value in the URL."""
    page.goto(f"{live_server.url}/calendar/list/")
    with page.expect_navigation():
        page.locator("input[name=date_from]").fill("2026-09-01")
        page.locator("input[name=date_from]").dispatch_event("change")
    expect(page).to_have_url(re.compile(r"date_from=2026-09-01"))


@pytest.mark.django_db(transaction=True)
def test_reset_link_clears_filters(page: Page, live_server):
    """The Reset link navigates to the plain list URL."""
    page.goto(f"{live_server.url}/calendar/list/?date_from=2026-01-01")
    # The Reset link lives inside the filter form (the header has a view switcher that
    # also points at the list URL), so scope the selector to the form.
    page.locator("#filter-form a[href*='calendar/list']").click()
    # After reset, no query params
    assert "date_from" not in page.url
