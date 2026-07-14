"""E2E: the author resubmits their own rejected competition from the profile (#200)."""

import datetime

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from tests.e2e.conftest import inject_session


@pytest.mark.django_db(transaction=True)
def test_author_resubmits_rejected_competition_from_profile(page: Page, live_server):
    author = User.objects.create_user(
        username="resub_e2e", email="resub_e2e@example.com", password="pw", role=User.Role.PARTICIPANT
    )
    comp = Competition.objects.create(
        title_ru="Rejected Race",
        date_start=datetime.date(2026, 9, 1),
        status=Competition.Status.REJECTED,
        submitted_by=author,
        rejection_reason="Please fix the date",
    )
    inject_session(page, live_server, author)
    page.goto(f"{live_server.url}{reverse('account_profile')}")

    # The rejected submission shows a Resubmit action; clicking it sends it back for review.
    resubmit = page.locator(f"form[action$='/{comp.pk}/resubmit/'] button")
    expect(resubmit).to_be_visible()
    resubmit.click()
    page.wait_for_load_state("networkidle")

    comp.refresh_from_db()
    assert comp.status == Competition.Status.PENDING_APPROVAL
