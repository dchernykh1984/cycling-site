"""E2E: a moderator can open a pending competition's page and approve it there (issue #180)."""

import pytest
from playwright.sync_api import Dialog, Page, expect

from calendar_app.models import Competition
from locations.models import Location, LocationProposal
from tests.e2e.conftest import UPCOMING, inject_session


@pytest.mark.django_db(transaction=True)
def test_moderator_approves_pending_from_detail_page(page: Page, live_server, superuser, organizer):
    comp = Competition.objects.create(
        title_ru="PendingModZ",
        title_en="PendingModZ",
        title_kk="PendingModZ",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.PENDING_APPROVAL,
    )
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/{comp.pk}/")

    # The pending page opens for a moderator and offers the approve action.
    approve_btn = page.locator(f'form[action="/ru/calendar/{comp.pk}/approve/"] button[type="submit"]')
    expect(approve_btn).to_be_visible()
    with page.expect_navigation():
        approve_btn.click()

    comp.refresh_from_db()
    assert comp.status == Competition.Status.APPROVED


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_rejecting_a_venue_asks_first(page: Page, live_server, superuser, organizer, language):
    region = Location.add_root(name_ru="RejectLandZ", name_en="RejectLandZ").add_child(name_ru="R", name_en="R")
    venue = Location.propose_venue(region.add_child(name_ru="C", name_en="C"), "RejectVenueZ", submitted_by=organizer)
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/{language}/calendar/moderate/")

    # The English question has an apostrophe ("city's"), which used to end the script's string: the
    # browser then rejected the venue without asking.
    questions = []

    def answer_no(dialog: Dialog) -> None:
        questions.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", answer_no)
    form = page.locator(f'form[action="/{language}/locations/{venue.pk}/reject/"]')
    form.locator("button[type=submit]").click()
    expect(form).to_be_visible()
    assert len(questions) == 1
    assert LocationProposal.objects.get(location=venue).status == LocationProposal.Status.PENDING_APPROVAL
