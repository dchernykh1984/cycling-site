"""E2E tests: registrations appear in the profile's 'My registrations' section.

Covers self_only, free (non-relay), free+relay, require_approval, require_payment,
and verifies that another user's registrations are not visible.
"""

import datetime

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from registrations.models import CompetitionRegistration, RegistrationCategory
from tests.e2e.conftest import UPCOMING, inject_session

PROFILE_PATH = "/accounts/profile/"


# ---------------------------------------------------------------------------
# shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rider(db):
    return User.objects.create_user(
        username="profile_rider",
        email="profile_rider@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        gender="M",
        birth_date=datetime.date(1990, 1, 1),
        first_name="Denis",
        last_name="Rider",
    )


@pytest.fixture
def other_rider(db):
    return User.objects.create_user(
        username="other_profile_rider",
        email="other_profile_rider@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        gender="F",
        birth_date=datetime.date(1992, 5, 15),
        first_name="Anna",
        last_name="Other",
    )


def _base_comp(**kwargs):
    defaults = {
        "title_ru": "Profile Test Race",
        "date_start": UPCOMING,
        "status": Competition.Status.APPROVED,
        "registration_enabled": True,
        "birth_date_mode": "year",
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _open_category(competition, name="Open"):
    return RegistrationCategory.objects.create(competition=competition, name=name, male=True, female=True)


def _make_reg(competition, user, **kwargs):
    defaults = {
        "competition": competition,
        "user": user,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "birth_date": user.birth_date,
        "gender": user.gender,
    }
    defaults.update(kwargs)
    return CompetitionRegistration.objects.create(**defaults)


def _go_profile(page, live_server):
    page.goto(f"{live_server.url}{PROFILE_PATH}")
    page.wait_for_load_state("networkidle")


def _fire_gender_change(page, value="M"):
    # The gender radio is pre-checked from the rider's profile; fire `change` to run the category
    # filter JS. locator.dispatch_event flakes on firefox under CI load, so wait for the element and
    # dispatch the event in-page via eval_on_selector, which is reliable across browsers.
    page.eval_on_selector(
        f"input[name='gender'][value='{value}']",
        "el => el.dispatchEvent(new Event('change', { bubbles: true }))",
    )


# ---------------------------------------------------------------------------
# self_only mode: registering yourself via the form
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_self_only_registration_appears_in_profile(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.SELF_ONLY,
    )
    _open_category(comp)
    inject_session(page, live_server, rider)

    page.goto(f"{live_server.url}/competitions/{comp.pk}/register/")
    page.select_option("select[name='category']", index=1)
    page.locator("#registration-form button[type='submit']").click()
    page.wait_for_url(f"{live_server.url}/competitions/{comp.pk}/participants/")

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_be_visible()


# ---------------------------------------------------------------------------
# free mode (non-relay): user enters own name/birth year manually
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_free_mode_registration_appears_in_profile(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.FREE,
    )
    _open_category(comp)
    inject_session(page, live_server, rider)

    page.goto(f"{live_server.url}/competitions/{comp.pk}/register/")
    page.fill("input[name='first_name']", "Denis")
    page.fill("input[name='last_name']", "Rider")
    page.fill("input[name='birth_year']", "1990")
    _fire_gender_change(page)
    page.select_option("select[name='category']", index=1)
    page.locator("#registration-form button[type='submit']").click()
    page.wait_for_url(f"{live_server.url}/competitions/{comp.pk}/participants/")

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_be_visible()


# ---------------------------------------------------------------------------
# relay: team registration appears in profile
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_relay_registration_appears_in_profile(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.FREE,
        relay_enabled=True,
        relay_max_members=3,
    )
    _open_category(comp, name="Mixed Relay")
    inject_session(page, live_server, rider)

    page.goto(f"{live_server.url}/competitions/{comp.pk}/register/")
    page.locator("input[name='participant_name']").first.fill("Ivanov Ivan")
    page.locator("input[name='participant_birth_year']").first.fill("1990")
    _fire_gender_change(page)
    expect(page.locator("select[name='category'] option", has_text="Mixed Relay")).to_be_attached()
    page.select_option("select[name='category']", label="Mixed Relay")
    page.locator("#registration-form button[type='submit']").click()
    page.wait_for_url(f"{live_server.url}/competitions/{comp.pk}/participants/")

    reg = CompetitionRegistration.objects.get(competition=comp)
    assert reg.user == rider

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_be_visible()


# ---------------------------------------------------------------------------
# require_approval: pending registration visible in profile with Pending badge
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_approval_required_registration_shows_pending_in_profile(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.FREE,
        require_approval=True,
    )
    _make_reg(comp, rider)
    inject_session(page, live_server, rider)

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_be_visible()
    expect(page.locator(".badge.bg-warning")).to_be_visible()


# ---------------------------------------------------------------------------
# require_payment: pending-payment registration visible in profile
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_payment_required_registration_shows_pending_in_profile(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.FREE,
        require_payment=True,
    )
    _make_reg(comp, rider, is_approved=True)
    inject_session(page, live_server, rider)

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_be_visible()
    expect(page.locator(".badge.bg-warning")).to_be_visible()


# ---------------------------------------------------------------------------
# approved registration: green Approved badge
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_approved_registration_shows_approved_badge_in_profile(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.FREE,
        require_approval=True,
    )
    _make_reg(comp, rider, is_approved=True)
    inject_session(page, live_server, rider)

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_be_visible()
    expect(page.locator(".badge.bg-success")).to_be_visible()


# ---------------------------------------------------------------------------
# security: another user's registration is not visible in my profile
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_other_users_registration_not_in_my_profile(page: Page, live_server, organizer, rider, other_rider):
    comp = _base_comp(submitted_by=organizer, registration_mode=Competition.RegistrationMode.FREE)
    _make_reg(comp, other_rider, first_name="Anna", last_name="Other")
    inject_session(page, live_server, rider)

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_have_count(0)


# ---------------------------------------------------------------------------
# issue #161: titles link to the competition page; deleted competitions are hidden
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_competition_title_links_to_detail_page(page: Page, live_server, organizer, rider):
    comp = _base_comp(submitted_by=organizer, registration_mode=Competition.RegistrationMode.FREE)
    _make_reg(comp, rider)
    inject_session(page, live_server, rider)

    _go_profile(page, live_server)
    link = page.get_by_role("link", name="Profile Test Race")
    expect(link).to_have_attribute("href", f"/calendar/{comp.pk}/")
    link.click()
    page.wait_for_url(f"{live_server.url}/calendar/{comp.pk}/")


@pytest.mark.django_db(transaction=True)
def test_deleted_competition_registration_hidden(page: Page, live_server, organizer, rider):
    comp = _base_comp(
        submitted_by=organizer,
        registration_mode=Competition.RegistrationMode.FREE,
        is_deleted=True,
    )
    _make_reg(comp, rider)
    inject_session(page, live_server, rider)

    _go_profile(page, live_server)
    expect(page.locator("text=Profile Test Race")).to_have_count(0)
    expect(page.locator(f"a[href='/calendar/{comp.pk}/']")).to_have_count(0)
