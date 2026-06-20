"""E2E for the on-site Quill editor of news articles (the shared rich_text_editor partial).

Real-browser coverage that the add/edit forms wire the shared editor (data-target/data-init,
hidden-tab sync) and round-trip the body into a saved NewsArticle. Mirrors the knowledge editor
tests; the body is set through the editor DOM and submitted in one synchronous step so the
MutationObserver revert race can't flake it on webkit.
"""

import pytest
from playwright.sync_api import Page, expect

from news.models import NewsArticle
from tests.e2e.conftest import inject_session


@pytest.mark.django_db(transaction=True)
def test_news_create_round_trips_body(page: Page, live_server, superuser):
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/news/articles/create/")  # published_at is pre-filled by the view
    page.fill("#id_title_ru", "E2E News Article")
    page.evaluate(
        """() => {
          document.querySelector('#quill-ru .ql-editor').innerHTML = '<p>News body in browser</p>';
          document.getElementById('id_title_ru').form.requestSubmit();
        }"""
    )
    page.wait_for_load_state("networkidle")

    article = NewsArticle.objects.get(title_ru="E2E News Article")
    assert "News body in browser" in article.body_ru

    # And it renders on the public detail page.
    page.goto(f"{live_server.url}/news/articles/{article.pk}/")
    expect(page.get_by_text("News body in browser")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_news_edit_round_trips_body(page: Page, live_server, superuser):
    article = NewsArticle.objects.create(title_ru="Editable News", body_ru="<p>Old body</p>")
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/news/articles/{article.pk}/edit/")
    expect(page.locator("#quill-ru .ql-editor")).to_contain_text("Old body")

    # Full innerHTML replace (old + new), then submit, in one synchronous step: the same pattern
    # the create test uses and which is reliable across engines. insertAdjacentHTML on a populated
    # Quill flaked on firefox (the appended node was lost before submit serialised the form).
    page.evaluate(
        """() => {
          const ed = document.querySelector('#quill-ru .ql-editor');
          ed.innerHTML = ed.innerHTML + '<p>added in edit</p>';
          document.getElementById('id_title_ru').form.requestSubmit();
        }"""
    )
    page.wait_for_load_state("networkidle")

    article.refresh_from_db()
    assert "added in edit" in article.body_ru
    assert "Old body" in article.body_ru  # the prefilled body survived the edit round-trip
