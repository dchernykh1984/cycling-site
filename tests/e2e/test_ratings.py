"""E2E for rating an event one took part in (issue #436): the banner's way to the review and away once it
is answered, the size of what is tapped on a phone in all three languages, and contrast in every skin."""

import datetime
import re
import uuid

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from event_photos.models import IssuedBib
from protocols.models import Protocol
from ratings import form
from ratings.models import Review
from registrations.models import CompetitionRegistration
from tests.e2e.conftest import inject_session
from tests.e2e.contrast import drawn, is_large, legibility, ratio
from tests.e2e.test_interface_rules import _frame
from tests.e2e.test_skin_contrast import NO_FADES, _in_state

# The event has no place, so its days are counted in UTC: two days back, it is over everywhere
OVER = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=2)
BANNER = "Rate the events you took part in"


@pytest.fixture
def rider(db):
    return User.objects.create_user(
        username="rider",
        email="rider@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        first_name="Dana",
        last_name="Kim",
    )


def _took_part(organizer, rider):
    """An event that is over, the rider's entry in it with bib 7, and 7 in its protocol's data."""
    event = Competition.objects.create(
        title_ru="Autumn Cup",
        title_en="Autumn Cup",
        date_start=OVER,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    entry = CompetitionRegistration.objects.create(
        competition=event,
        user=rider,
        first_name="Dana",
        last_name="Kim",
        birth_date=datetime.date(1990, 1, 1),
        gender="F",
    )
    IssuedBib.objects.create(competition=event, registration=entry, bib="7")
    columns = [{"id": "bib", "label": "Bib", "role": "bib"}]
    rows = [{"cells": {"bib": "7"}}]
    Protocol.objects.create(
        competition=event,
        protocol_type="absolute",
        document={"schema": 1, "sections": [{"type": "table", "columns": columns, "rows": rows}]},
    )
    return event


def _sign_in(page, live_server, user):
    page.context.clear_cookies()
    inject_session(page, live_server, user)


@pytest.mark.django_db(transaction=True)
def test_the_banner_leads_to_the_review_and_back_and_goes_once_it_is_sent(page: Page, live_server, organizer, rider):
    event = _took_part(organizer, rider)
    page.set_viewport_size({"width": 360, "height": 800})
    _sign_in(page, live_server, rider)
    page.goto(f"{live_server.url}/en/calendar/")
    banner = page.get_by_role("region", name=BANNER)
    expect(banner).to_contain_text("Autumn Cup")
    banner.get_by_role("link", name="Rate: Autumn Cup").click()
    expect(page).to_have_url(re.compile(rf"/en/ratings/events/{event.pk}/review/\?"))
    page.locator('label[for="overall-4"]').click()
    expect(page.get_by_role("radio", name="4")).to_be_checked()
    page.get_by_label("What went well, and what could be better").fill("Clear course")
    page.get_by_role("button", name="Send the review").click()
    expect(page.get_by_text("Thank you! Nobody will know the review is yours.")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/en/calendar/$"))  # back where the banner was tapped
    expect(page.get_by_role("region", name=BANNER)).to_have_count(0)
    assert Review.objects.get().answers == {"overall": 4, "comment": "Clear course"}


@pytest.mark.django_db(transaction=True)
def test_refusing_from_the_banner_stays_on_the_page_and_the_banner_goes(page: Page, live_server, organizer, rider):
    _took_part(organizer, rider)
    _sign_in(page, live_server, rider)
    page.goto(f"{live_server.url}/en/knowledge/")
    page.get_by_role("region", name=BANNER).get_by_role("button", name="Do not rate: Autumn Cup").click()
    expect(page.get_by_text("We will not ask about this event again.")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/en/knowledge/$"))
    expect(page.get_by_role("region", name=BANNER)).to_have_count(0)
    assert not Review.objects.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_on_a_phone_every_control_takes_a_tap_and_nothing_scrolls_sideways(
    page: Page, live_server, organizer, owner, rider, lang
):
    event = _took_part(organizer, rider)
    for score in (4, 5):  # the digest is offered from two reviews
        Review.objects.create(competition=event, form=form.VERSION, answers={form.RATED: score})
    User.objects.create_user(username="agent", email="agent@test.local", password="x", api_token=uuid.uuid4())
    page.set_viewport_size({"width": 360, "height": 800})
    small = []
    for user, path, controls in (
        (rider, "/calendar/", ".review-requests .btn"),
        (rider, f"/ratings/events/{event.pk}/review/", ".rating-review .btn"),
        (owner, "/calendar/", ".service-account-missing .btn"),
        (owner, "/accounts/profile/", ".service-accounts .btn, .service-account-pick"),
        (organizer, f"/ratings/events/{event.pk}/summary/", ".rating-summary .btn"),
        (organizer, "/ratings/", ".own-digests .list-group-item"),
    ):
        _sign_in(page, live_server, user)
        page.goto(f"{live_server.url}/{lang}{path}")
        assert page.evaluate("document.scrollingElement.scrollWidth <= document.scrollingElement.clientWidth"), path
        found = page.locator(controls).all()
        assert found, (path, controls)
        for control in found:
            box = control.bounding_box()
            # to a tenth of a pixel: Firefox lays a 44 px line out as 43.99997
            if box and min(round(box["height"], 1), round(box["width"], 1)) < 44:
                small.append((path, control.inner_text(), box["width"], box["height"]))
    assert not small, small


@pytest.mark.django_db(transaction=True)
def test_the_banner_and_the_review_page_read_in_this_skin(page: Page, live_server, organizer, rider):
    """The banner sits on the skin's warning colour: its buttons and the date stay 4.5:1 on it, at rest,
    under the pointer and in focus, and so do the review page's buttons."""
    event = _took_part(organizer, rider)
    _sign_in(page, live_server, rider)
    shortfalls = []
    for path, selector in (
        ("/en/news/", ".review-requests .btn, .review-requests .small"),
        (f"/en/ratings/events/{event.pk}/review/", ".rating-review .btn"),
    ):
        page.goto(f"{live_server.url}{path}")
        page.add_style_tag(content=NO_FADES)
        for control in page.locator(selector).all():
            for state in ("rest", "hover", "focus"):
                _in_state(page, control, state)
                value = legibility(control)
                if value < (3 if is_large(control) else 4.5):
                    shortfalls.append(f"{path} {control.inner_text()!r} ({state}): {value:.2f}")
    assert not shortfalls, shortfalls


@pytest.mark.django_db(transaction=True)
def test_the_chosen_score_stands_out_from_the_others_in_this_skin(page: Page, live_server, organizer, rider):
    """A score picked is filled or framed 3:1 apart from one not picked, as every selection on the site is.
    The dark skins paint outline buttons with !important and drew a picked score as an unpicked one."""
    event = _took_part(organizer, rider)
    _sign_in(page, live_server, rider)
    page.goto(f"{live_server.url}/en/ratings/events/{event.pk}/review/")
    page.add_style_tag(content=NO_FADES)
    chosen, other = page.locator('label[for="overall-3"]'), page.locator('label[for="overall-4"]')
    chosen.click()
    page.mouse.move(0, 0)
    expect(page.get_by_role("radio", name="3")).to_be_checked()
    fill = ratio(drawn(chosen, "fill"), drawn(other, "fill"))
    frame = ratio(_frame(chosen) or drawn(chosen, "fill"), _frame(other) or drawn(other, "fill"))
    assert max(fill, frame) >= 3, f"fill {fill:.2f}, frame {frame:.2f}"
    assert legibility(chosen) >= 4.5


@pytest.mark.django_db(transaction=True)
def test_an_organizers_own_events_under_the_ratings_read_in_this_skin(page: Page, live_server, organizer, rider):
    """Each of the organizer's events under the ratings reads 4.5:1, at rest, under the pointer and in focus."""
    event = _took_part(organizer, rider)
    for score in (4, 5):
        Review.objects.create(competition=event, form=form.VERSION, answers={form.RATED: score})
    _sign_in(page, live_server, organizer)
    page.goto(f"{live_server.url}/en/ratings/")
    page.add_style_tag(content=NO_FADES)
    rows = page.locator(".own-digests .list-group-item")
    expect(rows).to_have_count(1)
    shortfalls = []
    for state in ("rest", "hover", "focus"):
        _in_state(page, rows.first, state)
        for part in rows.first.locator("span").all():
            value = legibility(part)
            if value < (3 if is_large(part) else 4.5):
                shortfalls.append(f"{part.inner_text()!r} ({state}): {value:.2f}")
    assert not shortfalls, shortfalls
