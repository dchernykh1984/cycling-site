"""Invite-only events (issue #313), as a guest of the organizer meets them.

Before the invitation the event is nowhere -- not in the list, not at its own address. After opening
the link once while signed in, it is in the list like any other event, marked as by invitation.
"""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING, inject_session


@pytest.fixture
def private_event(db, organizer):
    return Competition.objects.create(
        title_ru="E2E Private Ride",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        invite_only=True,
    )


@pytest.fixture
def guest(db):
    return User.objects.create_user(
        username="e2e_guest",
        email="e2e_guest@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
    )


@pytest.mark.django_db(transaction=True)
def test_the_invitation_link_puts_the_event_on_the_guests_calendar(page: Page, live_server, private_event, guest):
    inject_session(page, live_server, guest)
    list_url = f"{live_server.url}/ru/calendar/list/?{AROUND_UPCOMING}"

    page.goto(list_url)
    expect(page.get_by_text("E2E Private Ride")).to_have_count(0)
    response = page.goto(f"{live_server.url}/ru/calendar/{private_event.pk}/")
    assert response is not None and response.status == 404

    page.goto(f"{live_server.url}/ru/calendar/{private_event.pk}/invite/{private_event.invite_key}/")
    # The key does not stay in the address bar: the link moves on to the event's own page.
    expect(page).to_have_url(f"{live_server.url}/ru/calendar/{private_event.pk}/")
    expect(page.locator("h1")).to_contain_text("E2E Private Ride")

    page.goto(list_url)
    row = page.locator("tr", has_text="E2E Private Ride")
    expect(row).to_be_visible()
    expect(row.locator(".badge")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_organizer_sees_the_link_to_hand_out(page: Page, live_server, private_event, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/calendar/{private_event.pk}/")
    expect(page.locator("#invite-url")).to_contain_text(f"/invite/{private_event.invite_key}/")
