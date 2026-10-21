"""Times are shown in the reader's own zone, which the page learns from the browser (issue #344)."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import CompetitionComment


@pytest.mark.browser_context_args(timezone_id="Asia/Tokyo")
@pytest.mark.django_db(transaction=True)
def test_a_comment_time_follows_the_browsers_zone(page: Page, live_server, approved_competition, organizer):
    comment = CompetitionComment.objects.create(competition=approved_competition, author=organizer, body="hi")
    CompetitionComment.objects.filter(pk=comment.pk).update(
        created_at=datetime.datetime(2026, 9, 1, 12, 0, tzinfo=datetime.UTC)
    )
    url = f"{live_server.url}/ru/calendar/{approved_competition.pk}/"

    # The first page is written before the server knows the zone; it is what tells it.
    page.goto(url)
    assert {c["name"]: c["value"] for c in page.context.cookies()}.get("tz") == "Asia/Tokyo"

    page.goto(url)
    expect(page.get_by_text("01.09.2026 21:00")).to_be_visible()
