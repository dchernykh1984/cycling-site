"""E2E: entities created through the REST API show up on the public front.

These tests make a real HTTP request to the live server's /api/v1/ endpoints
(via Playwright's APIRequestContext) with an admin token, then load the public
page in the browser and assert the new content is visible. The default
django_language cookie is "ru" (see conftest), so assertions use the ru title.
"""

import datetime
import json
import uuid

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User


@pytest.fixture
def api_admin(db):
    return User.objects.create_user(
        username="e2e_api_admin",
        email="e2e_api_admin@test.local",
        password="TestPass123!",
        role=User.Role.ADMIN,
        api_token=uuid.uuid4(),
    )


def _api_post(page, url, token, payload):
    return page.request.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(payload),
    )


@pytest.mark.django_db(transaction=True)
def test_news_article_created_via_api_appears_on_front(page: Page, live_server, api_admin):
    resp = _api_post(
        page,
        f"{live_server.url}/api/v1/news/",
        api_admin.api_token,
        {
            "title": {"ru": "E2E API News RU", "kk": "E2E API News KK", "en": "E2E API News EN"},
            "intro": {"ru": "Intro RU", "kk": "Intro KK", "en": "Intro EN"},
            "body": {
                "ru": "<h2>Razdel</h2><p>Telo novosti RU</p>",
                "kk": "<h2>Bolim</h2><p>Telo novosti KK</p>",
                "en": "<h2>Section</h2><p>News body EN</p>",
            },
        },
    )
    assert resp.status == 201, resp.text()
    article_id = resp.json()["id"]

    # Front list page shows the ru title.
    page.goto(f"{live_server.url}/ru/news/")
    expect(page.get_by_text("E2E API News RU")).to_be_visible()

    # Detail page renders the rich HTML body unescaped (heading element, not text).
    page.goto(f"{live_server.url}/ru/news/articles/{article_id}/")
    expect(page.locator("h2", has_text="Razdel")).to_be_visible()
    expect(page.get_by_text("Telo novosti RU")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_competition_created_via_api_appears_on_front(page: Page, live_server, api_admin):
    resp = _api_post(
        page,
        f"{live_server.url}/api/v1/competitions/",
        api_admin.api_token,
        {
            "title": {"ru": "E2E API Race RU", "kk": "E2E API Race KK", "en": "E2E API Race EN"},
            # Default list range is today..today+30d, so pick a date inside it.
            "date_start": (datetime.date.today() + datetime.timedelta(days=7)).isoformat(),
        },
    )
    assert resp.status == 201, resp.text()

    # Admin-created competitions are auto-approved, so they show on the public list.
    page.goto(f"{live_server.url}/ru/calendar/list/")
    expect(page.get_by_text("E2E API Race RU")).to_be_visible()
