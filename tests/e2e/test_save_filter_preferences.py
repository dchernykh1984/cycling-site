"""Saving the calendar filter into preferences (issue #322), as a member uses it."""

import re
import time

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session, open_filter_panel


def _member(**extra):
    return User.objects.create_user(
        username="e2e_saver", email="e2e_saver@test.local", password="testpass123!", role=User.Role.PARTICIPANT, **extra
    )


def _saved_types(user, timeout=10.0):
    """The member's saved event types, once the browser's request has landed."""
    deadline = time.monotonic() + timeout
    while True:
        saved = set(user.preferred_event_types.values_list("pk", flat=True))
        if saved or time.monotonic() > deadline:
            return saved
        time.sleep(0.2)


@pytest.mark.django_db(transaction=True)
def test_the_button_saves_the_filter_and_the_next_visit_opens_with_it(page: Page, live_server, race_event_type):
    race = race_event_type
    member = _member()
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/calendar/list/?event_type={race.pk}")
    open_filter_panel(page)

    button = page.locator("#save-filter-btn")
    button.click()
    expect(button).to_be_disabled()
    assert _saved_types(member) == {race.pk}

    page.goto(f"{live_server.url}/ru/calendar/list/")
    open_filter_panel(page)
    expect(page).to_have_url(re.compile(rf"event_type={race.pk}"))


@pytest.mark.django_db(transaction=True)
def test_with_always_save_a_change_on_the_calendar_is_kept(page: Page, live_server, race_event_type):
    race = race_event_type
    member = _member(autosave_filters=True)
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/calendar/?reset=1")
    expect(page.locator("#save-filter-btn")).to_have_count(0)
    page.wait_for_load_state("load")

    open_filter_panel(page)
    page.locator("#et-btn-1").click()
    page.locator(f"#et-menu-1 input.mf-item[value='{race.pk}']").check()
    assert _saved_types(member) == {race.pk}


@pytest.mark.django_db(transaction=True)
def test_with_always_save_reset_clears_the_saved_filter(page: Page, live_server, race_event_type):
    race = race_event_type
    member = _member(autosave_filters=True)
    member.preferred_event_types.add(race)
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/calendar/list/?event_type={race.pk}")
    open_filter_panel(page)
    page.wait_for_load_state("load")
    page.locator("a[href*='reset=1']").click()
    page.wait_for_url(re.compile(r"reset=1"))
    deadline = time.monotonic() + 10
    while member.preferred_event_types.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not member.preferred_event_types.exists()
