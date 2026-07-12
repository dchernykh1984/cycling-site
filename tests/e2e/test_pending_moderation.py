"""E2E: a moderator can open a pending competition's page and approve it there (issue #180)."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import inject_session


@pytest.mark.django_db(transaction=True)
def test_moderator_approves_pending_from_detail_page(page: Page, live_server, superuser, organizer):
    comp = Competition.objects.create(
        title_ru="PendingModZ",
        title_en="PendingModZ",
        title_kk="PendingModZ",
        date_start=datetime.date(2026, 9, 20),
        submitted_by=organizer,
        status=Competition.Status.PENDING_APPROVAL,
    )
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/calendar/{comp.pk}/")

    # The pending page opens for a moderator and offers the approve action.
    approve_btn = page.locator(f'form[action="/calendar/{comp.pk}/approve/"] button[type="submit"]')
    expect(approve_btn).to_be_visible()
    with page.expect_navigation():
        approve_btn.click()

    comp.refresh_from_db()
    assert comp.status == Competition.Status.APPROVED
