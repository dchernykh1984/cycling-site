"""E2E tests for the competition calendar view (FullCalendar)."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db(transaction=True)
def test_calendar_shows_month_grid_by_default(page: Page, live_server):
    """Calendar must open in dayGridMonth view on both desktop and mobile."""
    page.goto(f"{live_server.url}/calendar/")
    expect(page.locator(".fc")).to_be_visible()
    expect(page.locator(".fc-dayGridMonth-view")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_calendar_has_no_view_toggle_button(page: Page, live_server):
    """The right headerToolbar section must have no view-switch buttons."""
    page.goto(f"{live_server.url}/calendar/")
    expect(page.locator(".fc")).to_be_visible()
    # headerToolbar right is '' - the last toolbar chunk must contain no fc-button
    expect(page.locator(".fc-header-toolbar .fc-toolbar-chunk:last-child .fc-button")).to_have_count(0)
