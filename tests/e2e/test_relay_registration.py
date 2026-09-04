"""E2E tests for relay/team registration feature."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from registrations.models import CompetitionRegistration, RegistrationCategory
from tests.e2e.conftest import UPCOMING, inject_session

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def relay_competition(db, organizer):
    return Competition.objects.create(
        title_ru="Relay Race",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        birth_date_mode="year",
        relay_enabled=True,
        relay_max_members=3,
    )


@pytest.fixture
def relay_category(db, relay_competition):
    return RegistrationCategory.objects.create(
        competition=relay_competition,
        name="Mixed Relay",
        male=True,
        female=True,
    )


@pytest.fixture
def participant_user(db):

    return User.objects.create_user(
        username="relay_rider",
        email="relay_rider@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        gender="M",
        birth_date=datetime.date(1990, 1, 1),
    )


# ---------------------------------------------------------------------------
# competition settings form: relay checkbox shows/hides max-members field
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_relay_max_wrap_hidden_by_default(page: Page, live_server, organizer):
    """relay_max_members field is hidden until 'Allow relay' checkbox is ticked."""
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/calendar/submit/")
    page.locator("#reg_enabled").check()
    expect(page.locator("#relay_max_wrap")).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_relay_max_wrap_shown_when_relay_enabled(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/calendar/submit/")
    page.locator("#reg_enabled").check()
    page.locator("#relay_enabled").check()
    expect(page.locator("#relay_max_wrap")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_relay_max_wrap_hides_when_relay_unchecked_again(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/calendar/submit/")
    page.locator("#reg_enabled").check()
    page.locator("#relay_enabled").check()
    page.locator("#relay_enabled").uncheck()
    expect(page.locator("#relay_max_wrap")).to_have_css("display", "none")


# ---------------------------------------------------------------------------
# registration form: relay UI rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_relay_form_shows_member_rows_instead_of_first_last(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """When relay_enabled, register form must show participant name rows, not first/last name inputs."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    # Relay name input must be present
    expect(page.locator("input[name='participant_name']")).to_be_visible()
    # Standard first/last name inputs must not be present
    expect(page.locator("input[name='first_name']")).to_have_count(0)
    expect(page.locator("input[name='last_name']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_relay_form_add_member_button_adds_row(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """Clicking '+ Add member' appends a new input row."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    initial_count = page.locator("input[name='participant_name']").count()
    page.click("#add-relay-member-btn")
    expect(page.locator("input[name='participant_name']")).to_have_count(initial_count + 1)


@pytest.mark.django_db(transaction=True)
def test_relay_form_add_button_disabled_at_max(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """'+ Add member' button becomes disabled once relay_max_members is reached."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    # Fill up to max (relay_max_members=3, 1 row already present)
    page.click("#add-relay-member-btn")
    page.click("#add-relay-member-btn")

    expect(page.locator("input[name='participant_name']")).to_have_count(3)
    # Button must now be disabled
    expect(page.locator("#add-relay-member-btn")).to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_relay_form_remove_button_hidden_for_single_member(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """Remove button must be hidden when there is only one member row."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    remove_btn = page.locator(".remove-relay-member").first
    expect(remove_btn).to_have_css("display", "none")


@pytest.mark.django_db(transaction=True)
def test_relay_form_remove_button_visible_with_multiple_members(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """Remove button becomes visible once there are two or more member rows."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    page.click("#add-relay-member-btn")
    expect(page.locator(".remove-relay-member").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_relay_form_remove_button_removes_row(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """The '-' remove button removes the corresponding row."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    page.click("#add-relay-member-btn")
    expect(page.locator("input[name='participant_name']")).to_have_count(2)

    page.locator(".remove-relay-member").last.click()
    expect(page.locator("input[name='participant_name']")).to_have_count(1)


# ---------------------------------------------------------------------------
# registration form: submission
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_relay_registration_submit_creates_record(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """Submitting relay form with 2 members creates a CompetitionRegistration with participant_names."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    # Fill first member (name, birth year, city)
    page.locator("input[name='participant_name']").first.fill("Ivanov Ivan")
    page.locator("input[name='participant_birth_year']").first.fill("1990")
    page.locator("input[name='participant_city']").first.fill("Almaty")

    # Add second member
    page.click("#add-relay-member-btn")
    page.locator("input[name='participant_name']").nth(1).fill("Petrov Vasya")
    page.locator("input[name='participant_birth_year']").nth(1).fill("1995")
    page.locator("input[name='participant_city']").nth(1).fill("Moscow")

    # Trigger updateCategories (fires again if gender radio was already M)
    page.locator("input[name='gender'][value='M']").dispatch_event("change")

    # Wait for category option to appear and select it
    expect(page.locator("select[name='category'] option", has_text="Mixed Relay")).to_be_attached()
    page.select_option("select[name='category']", label="Mixed Relay")

    page.locator("#registration-form button[type='submit']").click()

    # Should redirect to participant list
    page.wait_for_url(f"{live_server.url}/ru/competitions/{relay_competition.pk}/participants/")

    reg = CompetitionRegistration.objects.get(competition=relay_competition)
    assert reg.participant_names == "Ivanov Ivan<BR>Petrov Vasya"
    assert reg.participant_birth_years == "1990<BR>1995"
    assert reg.participant_cities == "Almaty<BR>Moscow"
    assert reg.first_name == ""
    assert reg.last_name == ""


# ---------------------------------------------------------------------------
# participant list: relay names rendered correctly
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_participant_list_shows_relay_names(page: Page, live_server, organizer, relay_competition):
    """Relay registration names are visible in the participant list (rendered via |safe)."""
    CompetitionRegistration.objects.create(
        competition=relay_competition,
        first_name="",
        last_name="",
        participant_names="Kozlov Artem<BR>Dyakov Nikolay",
        birth_date=datetime.date(1990, 1, 1),
        gender="M",
    )
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/participants/")

    # Both names must appear in the table cell
    expect(page.locator("text=Kozlov Artem")).to_be_visible()
    expect(page.locator("text=Dyakov Nikolay")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_individual_competition_shows_first_last_name_inputs(page: Page, live_server, participant_user, db, organizer):
    """Non-relay competition must show standard first/last name inputs, not relay rows."""
    comp = Competition.objects.create(
        title_ru="Individual Race RU",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        birth_date_mode="year",
        relay_enabled=False,
    )
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{comp.pk}/register/")

    expect(page.locator("input[name='last_name']")).to_be_visible()
    expect(page.locator("input[name='first_name']")).to_be_visible()
    expect(page.locator("#relay-names-container")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_individual_registration_still_shows_last_first(page: Page, live_server, organizer, relay_competition):
    """Individual entries still display last_name + first_name in participant list."""
    CompetitionRegistration.objects.create(
        competition=relay_competition,
        first_name="Ivan",
        last_name="Testov",
        birth_date=datetime.date(1990, 1, 1),
        gender="M",
    )
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/participants/")

    expect(page.locator("text=Testov Ivan")).to_be_visible()


# ---------------------------------------------------------------------------
# profile: relay registration appears in personal account
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_relay_registration_appears_in_user_profile(
    page: Page, live_server, participant_user, relay_competition, relay_category
):
    """After submitting a relay registration, it must appear in the user's profile under 'My registrations'."""
    inject_session(page, live_server, participant_user)
    page.goto(f"{live_server.url}/ru/competitions/{relay_competition.pk}/register/")

    page.locator("input[name='participant_name']").first.fill("Ivanov Ivan")
    page.locator("input[name='participant_birth_year']").first.fill("1990")
    page.locator("input[name='participant_city']").first.fill("Almaty")

    page.locator("input[name='gender'][value='M']").dispatch_event("change")
    expect(page.locator("select[name='category'] option", has_text="Mixed Relay")).to_be_attached()
    page.select_option("select[name='category']", label="Mixed Relay")

    page.locator("#registration-form button[type='submit']").click()
    page.wait_for_url(f"{live_server.url}/ru/competitions/{relay_competition.pk}/participants/")

    page.goto(f"{live_server.url}/ru/accounts/profile/")
    # An entry still open shows twice on the profile: as a card and as a row of the table below.
    expect(page.locator("table >> text=Relay Race")).to_be_visible()
