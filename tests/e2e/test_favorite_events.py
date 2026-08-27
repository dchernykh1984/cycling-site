"""E2E tests for favorite events (issue #183): the detail-page star and the list filter."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition, CompetitionFavorite
from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING, inject_session


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
    expect(page.get_by_role("link", name="FavoriteRaceZ")).to_be_visible()
    expect(page.get_by_role("link", name="PlainRaceZ")).to_be_visible()

    # The checkbox auto-submits the filter form.
    with page.expect_navigation():
        page.locator("#favorite-filter").check()

    expect(page.locator("#favorite-filter")).to_be_checked()
    expect(page.get_by_role("link", name="FavoriteRaceZ")).to_be_visible()
    expect(page.get_by_role("link", name="PlainRaceZ")).to_have_count(0)
