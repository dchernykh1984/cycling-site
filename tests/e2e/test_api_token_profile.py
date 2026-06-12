"""E2E tests for the API token section on the profile page."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session


def _profile_url(live_server):
    return f"{live_server.url}/accounts/profile/"


@pytest.fixture
def organizer_with_token(db):
    import uuid

    user = User.objects.create_user(
        username="e2e_token_org",
        email="e2e_token_org@test.local",
        password="TestPass123!",
        role=User.Role.ORGANIZER,
        api_token=uuid.uuid4(),
    )
    return user


@pytest.fixture
def organizer_no_token(db):
    return User.objects.create_user(
        username="e2e_no_token_org",
        email="e2e_no_token_org@test.local",
        password="TestPass123!",
        role=User.Role.ORGANIZER,
    )


@pytest.fixture
def participant_user(db):
    return User.objects.create_user(
        username="e2e_participant",
        email="e2e_participant@test.local",
        password="TestPass123!",
        role=User.Role.PARTICIPANT,
    )


@pytest.mark.django_db(transaction=True)
def test_api_section_visible_for_organizer(page: Page, live_server, organizer_with_token):
    inject_session(page, live_server, organizer_with_token)
    page.goto(_profile_url(live_server))
    expect(page.locator(".card-header", has_text="API")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_api_token_displayed_for_organizer(page: Page, live_server, organizer_with_token):
    inject_session(page, live_server, organizer_with_token)
    page.goto(_profile_url(live_server))
    token_str = str(organizer_with_token.api_token)
    expect(page.locator(f"[value='{token_str}'], code:has-text('{token_str}')")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_regenerate_form_present_when_no_token(page: Page, live_server, organizer_no_token):
    inject_session(page, live_server, organizer_no_token)
    page.goto(_profile_url(live_server))
    # The form for generating/regenerating a token should be present
    expect(page.locator("form[action*='api-token/regenerate']")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_api_section_absent_for_participant(page: Page, live_server, participant_user):
    inject_session(page, live_server, participant_user)
    page.goto(_profile_url(live_server))
    # Participants (rank < 2) should not see the API section at all
    expect(page.locator("form[action*='api-token/regenerate']")).not_to_be_visible()
