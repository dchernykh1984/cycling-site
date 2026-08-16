"""E2E tests for participant list button visibility and approve/reject workflow."""

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import UPCOMING, inject_session


def _goto_participants(page, live_server, user, competition):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/competitions/{competition.pk}/participants/")


# ---------------------------------------------------------------------------
# approve / reject button visibility
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_approve_reject_buttons_visible_when_approval_required(
    page: Page, live_server, organizer, competition_with_approval, registration
):
    _goto_participants(page, live_server, organizer, competition_with_approval)
    # Approve button is visible for a pending registration
    expect(page.locator("form[action*='/approve/'] button")).to_be_visible()
    # Reject button is visible
    expect(page.locator("button[data-bs-target*='reject']")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_approve_reject_buttons_hidden_without_approval(page: Page, live_server, organizer, db):
    """When require_approval=False, approve/reject buttons must not appear."""

    comp = Competition.objects.create(
        title_ru="No Approval RU",
        title_en="No Approval",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        require_approval=False,
        require_payment=False,
    )
    import datetime as dt

    from registrations.models import CompetitionRegistration

    CompetitionRegistration.objects.create(
        competition=comp,
        first_name="Test",
        last_name="User",
        birth_date=dt.date(1990, 1, 1),
        gender="M",
    )
    _goto_participants(page, live_server, organizer, comp)
    expect(page.locator("form[action*='/approve/'] button")).to_have_count(0)
    expect(page.locator("button[data-bs-target*='reject']")).to_have_count(0)


# ---------------------------------------------------------------------------
# mark paid button visibility
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_mark_paid_visible_when_payment_required(
    page: Page, live_server, organizer, competition_with_approval, registration
):
    _goto_participants(page, live_server, organizer, competition_with_approval)
    expect(page.locator("form[action*='/mark-paid/'] button")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_mark_paid_hidden_without_payment(page: Page, live_server, organizer, db):
    import datetime as dt

    comp = Competition.objects.create(
        title_ru="No Payment RU",
        title_en="No Payment",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        require_approval=False,
        require_payment=False,
    )
    from registrations.models import CompetitionRegistration

    CompetitionRegistration.objects.create(
        competition=comp,
        first_name="Test",
        last_name="User",
        birth_date=dt.date(1990, 1, 1),
        gender="M",
    )
    _goto_participants(page, live_server, organizer, comp)
    expect(page.locator("form[action*='/mark-paid/'] button")).to_have_count(0)


# ---------------------------------------------------------------------------
# approve button visible for rejected participant
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_approve_button_visible_for_rejected_participant(
    page: Page, live_server, organizer, competition_with_approval, rejected_registration
):
    """After rejection, Approve button must remain available (to undo rejection)."""
    _goto_participants(page, live_server, organizer, competition_with_approval)
    # Rejected row: approve button must exist
    expect(page.locator("form[action*='/approve/'] button")).to_be_visible()
    # Reject button must NOT be shown for already-rejected participant
    expect(page.locator("button[data-bs-target*='reject']")).to_have_count(0)


# ---------------------------------------------------------------------------
# approved / paid columns only shown when feature is enabled
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_approved_column_hidden_without_approval(page: Page, live_server, organizer, db):

    comp = Competition.objects.create(
        title_ru="No Approval Col RU",
        title_en="No Approval Col",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
        require_approval=False,
        require_payment=False,
    )
    _goto_participants(page, live_server, organizer, comp)
    # "Approved" column header must not appear for manager when require_approval=False
    header_texts = page.locator("table thead th").all_inner_texts()
    assert not any("approved" in t.lower() for t in header_texts)


@pytest.mark.django_db(transaction=True)
def test_participant_list_no_horizontal_scroll_with_long_values(page: Page, live_server, organizer, db):
    """Long names / city values must wrap (overflow-wrap), not push the participant table past
    its container and produce a horizontal scrollbar."""
    import datetime

    from registrations.models import CompetitionRegistration

    long = "Averyveryverylongunbreakableplaceholdervalueforlayouttest"
    comp = Competition.objects.create(
        title_ru="Scroll Test RU",
        title_en="Scroll Test",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
    )
    CompetitionRegistration.objects.create(
        competition=comp,
        first_name=long,
        last_name=long,
        city=long,
        birth_date=datetime.date(1990, 1, 1),
        gender="M",
    )
    inject_session(page, live_server, organizer)
    page.set_viewport_size({"width": 1200, "height": 800})
    page.goto(f"{live_server.url}/competitions/{comp.pk}/participants/")
    expect(page.locator(".participant-list-table")).to_be_visible()
    overflow = page.evaluate(
        "() => { const el = document.querySelector('.table-responsive'); return el.scrollWidth - el.clientWidth; }"
    )
    assert overflow <= 1, f"participant list overflows horizontally by {overflow}px"


@pytest.mark.django_db(transaction=True)
def test_participant_list_stacks_into_cards_on_mobile(page: Page, live_server, organizer, db):
    """On a phone-width viewport the participant table renders as stacked cards: the header row
    is hidden, every data cell exposes its column name via data-label, and there is no
    horizontal scroll (mirrors the calendar list's mobile card layout)."""
    import datetime

    from registrations.models import CompetitionRegistration

    comp = Competition.objects.create(
        title_ru="Cards Test RU",
        title_en="Cards Test",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
    )
    CompetitionRegistration.objects.create(
        competition=comp,
        first_name="Denis",
        last_name="Chernykh",
        city="Almaty",
        birth_date=datetime.date(1984, 1, 1),
        gender="M",
    )
    inject_session(page, live_server, organizer)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/competitions/{comp.pk}/participants/")

    expect(page.locator(".participant-list-table thead")).to_be_hidden()
    expect(page.locator(".participant-list-table td[data-label]").first).to_be_visible()
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 1, f"mobile participant list overflows horizontally by {overflow}px"
