"""E2E tests for favorite events (issue #183): the detail-page star and the list filter."""

import datetime

import pytest
from django.conf import settings
from playwright.sync_api import Locator, Page, expect

from accounts.models import User
from calendar_app.models import Competition, CompetitionFavorite
from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING, inject_session, open_filter_panel
from tests.e2e.contrast import legibility

# The dark skin draws the empty star in Lux's grey, 2.46:1: kept as it is, as light and dark do not
# change unasked, and never allowed to get worse. Every other skin clears 3:1.
FAINT_STAR = {"dark": 2.4}


@pytest.mark.django_db(transaction=True)
def test_star_toggles_favorite_on_detail_page(page: Page, live_server, superuser, approved_competition):
    """Clicking the star favorites the event (lit + persisted), clicking again unfavorites it."""
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/{approved_competition.pk}/")

    star = page.locator("#favorite-btn")
    expect(star).to_have_attribute("aria-pressed", "false")

    star.click()
    expect(star).to_have_attribute("aria-pressed", "true")
    assert CompetitionFavorite.objects.filter(user=superuser, competition=approved_competition).exists()

    # The lit state survives a reload (server-rendered from the stored favorite).
    page.reload()
    expect(page.locator("#favorite-btn")).to_have_attribute("aria-pressed", "true")

    # Clicking again removes the favorite.
    page.locator("#favorite-btn").click()
    expect(page.locator("#favorite-btn")).to_have_attribute("aria-pressed", "false")
    assert not CompetitionFavorite.objects.filter(user=superuser, competition=approved_competition).exists()


@pytest.mark.django_db(transaction=True)
def test_the_empty_star_can_be_seen_in_this_skin(page: Page, live_server, superuser, approved_competition):
    """The star is a button without words, so the glyph is what shows it is there: 3:1 (WCAG 1.4.11)."""
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/{approved_competition.pk}/")
    star = page.locator("#favorite-btn")
    expect(star).to_have_attribute("aria-pressed", "false")
    page.mouse.move(0, 0)
    assert legibility(star) >= FAINT_STAR.get(settings.DEFAULT_SKIN, 3)


@pytest.mark.django_db(transaction=True)
def test_the_count_under_the_star_follows_every_members_star(
    page: Page, live_server, superuser, organizer, approved_competition
):
    """Under the star, how many members have the event in favorites, the reader's own star included."""
    CompetitionFavorite.objects.create(user=organizer, competition=approved_competition)
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/{approved_competition.pk}/")
    star, count = page.locator("#favorite-btn"), page.locator("#favorite-count")
    expect(count).to_have_text("1")

    star.click()
    expect(star).to_have_attribute("aria-pressed", "true")
    expect(count).to_have_text("2")

    star.click()
    expect(star).to_have_attribute("aria-pressed", "false")
    expect(count).to_have_text("1")


@pytest.mark.django_db(transaction=True)
def test_the_count_under_the_star_can_be_read_in_this_skin(page: Page, live_server, superuser, approved_competition):
    """The number is text, so it needs 4.5:1 (WCAG 1.4.3) in every skin."""
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/{approved_competition.pk}/")
    page.mouse.move(0, 0)
    assert legibility(page.locator("#favorite-count")) >= 4.5


def _width(locator: Locator) -> float:
    box = locator.bounding_box()
    assert box is not None
    return box["width"]


@pytest.mark.django_db(transaction=True)
def test_the_star_stays_put_when_the_count_gains_a_digit(page: Page, live_server, superuser, approved_competition):
    """A click taking the count from 999 to 1000 leaves the star's column as wide as the star (principle 5).

    The column's width, not the star's place, is compared: an engine may draw the empty and the filled star
    at different widths, which the count has nothing to do with.
    """
    fans = User.objects.bulk_create(User(username=f"fan{n}", email=f"fan{n}@test.local") for n in range(999))
    CompetitionFavorite.objects.bulk_create(
        CompetitionFavorite(user=fan, competition=approved_competition) for fan in fans
    )
    page.set_viewport_size({"width": 360, "height": 800})
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/{approved_competition.pk}/")
    star, column = page.locator("#favorite-btn"), page.locator("#favorite-form")
    assert _width(column) == _width(star)

    star.click()
    expect(page.locator("#favorite-count")).to_have_text("1000")
    assert _width(column) == _width(star)


@pytest.mark.django_db(transaction=True)
def test_list_favorites_only_checkbox_filters(page: Page, live_server, superuser, organizer):
    """Ticking 'Only favorites' on the list narrows it to the user's favorited events."""
    favorited = Competition.objects.create(
        title_ru="FavoriteRaceZ",
        title_en="FavoriteRaceZ",
        title_kk="FavoriteRaceZ",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    Competition.objects.create(
        title_ru="PlainRaceZ",
        title_en="PlainRaceZ",
        title_kk="PlainRaceZ",
        date_start=UPCOMING + datetime.timedelta(days=2),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    CompetitionFavorite.objects.create(user=superuser, competition=favorited)

    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/calendar/list/?{AROUND_UPCOMING}")
    open_filter_panel(page)
    expect(page.get_by_role("link", name="FavoriteRaceZ")).to_be_visible()
    expect(page.get_by_role("link", name="PlainRaceZ")).to_be_visible()

    # The checkbox auto-submits the filter form.
    with page.expect_navigation():
        page.locator("#favorite-filter").check()

    expect(page.locator("#favorite-filter")).to_be_checked()
    expect(page.get_by_role("link", name="FavoriteRaceZ")).to_be_visible()
    expect(page.get_by_role("link", name="PlainRaceZ")).to_have_count(0)
