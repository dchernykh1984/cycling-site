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
from knowledge.models import DraftSubmission


@pytest.fixture
def api_admin(db):
    return User.objects.create_user(
        username="e2e_api_admin",
        email="e2e_api_admin@test.local",
        password="TestPass123!",
        role=User.Role.ADMIN,
        api_token=uuid.uuid4(),
    )


@pytest.fixture
def knowledge_index(db, wagtail_home_page):
    """Guarantee a live ru KnowledgeIndexPage so approved knowledge drafts have a parent.

    The migration-created index pages are flushed in the transactional e2e DB (they exist
    locally but not in CI), so approve() would otherwise fail with 'No live
    KnowledgeIndexPage'. The article may end up under a different index than this one when
    several exist, so the test navigates via the created article rather than this object.
    """
    from wagtail.models import Page, Site

    from knowledge.models import KnowledgeIndexPage

    site = Site.objects.filter(is_default_site=True).first()
    root = site.root_page if site else Page.objects.filter(depth=1).first()
    index = KnowledgeIndexPage(title="Knowledge Base", slug="knowledge-base")
    root.add_child(instance=index)
    index.save_revision().publish()
    return KnowledgeIndexPage.objects.get(pk=index.pk)


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
        f"{live_server.url}/api/v1/news/articles/",
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
    page.goto(f"{live_server.url}/news/")
    expect(page.get_by_text("E2E API News RU")).to_be_visible()

    # Detail page renders the rich HTML body unescaped (heading element, not text).
    page.goto(f"{live_server.url}/news/articles/{article_id}/")
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
    page.goto(f"{live_server.url}/calendar/list/")
    expect(page.get_by_text("E2E API Race RU")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_knowledge_article_created_via_api_appears_on_front(page: Page, live_server, api_admin, knowledge_index):
    resp = _api_post(
        page,
        f"{live_server.url}/api/v1/knowledge/",
        api_admin.api_token,
        {
            "title": "E2E API Knowledge RU",
            "body": "<h2>Glava</h2><p>Telo statyi</p>",
            "locale": "ru",
            "category": "",
        },
    )
    # Admin POST auto-approves the draft, which creates a live KnowledgeArticlePage
    # under the ru KnowledgeIndexPage (guaranteed by the knowledge_index fixture).
    assert resp.status == 201, resp.text()
    assert resp.json()["status"] == DraftSubmission.Status.APPROVED

    from knowledge.models import KnowledgeArticlePage

    article = KnowledgeArticlePage.objects.get(slug="e2e-api-knowledge-ru")

    # The article page renders its title and rich HTML body on the public front.
    page.goto(f"{live_server.url}{article.url}")
    expect(page.get_by_role("heading", name="E2E API Knowledge RU")).to_be_visible()
    expect(page.get_by_text("Telo statyi")).to_be_visible()

    # It is also listed on its knowledge index page.
    page.goto(f"{live_server.url}{article.get_parent().url}")
    expect(page.get_by_text("E2E API Knowledge RU").first).to_be_visible()
