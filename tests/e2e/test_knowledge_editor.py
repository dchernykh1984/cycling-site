"""E2E tests for the on-site Quill editor of the knowledge base (KnowledgeArticle).

Real-browser coverage: the add/edit forms render a working Quill editor, round-trip the
body into a saved article, and the server strips scripts. Mirrors the competition editor
tests but for the single-body knowledge form.
"""

import pytest
from playwright.sync_api import Page, expect

from knowledge.models import KnowledgeArticle, KnowledgeIndexPage
from tests.e2e.conftest import inject_session

_SNOW_LOADED = """() => {
  const s = [...document.styleSheets].find(x => x.href && x.href.includes('quill.snow'));
  try { return s ? s.cssRules.length : 0; } catch (e) { return -1; }
}"""


@pytest.fixture
def knowledge_index(db, wagtail_home_page):
    """A live ru KnowledgeIndexPage so a created article's URL resolves."""
    from wagtail.models import Page, Site

    site = Site.objects.filter(is_default_site=True).first()
    root = site.root_page if site else Page.objects.filter(depth=1).first()
    index = KnowledgeIndexPage(title="Knowledge Base", slug="knowledge-base")
    root.add_child(instance=index)
    index.save_revision().publish()
    return KnowledgeIndexPage.objects.get(pk=index.pk)


def _assert_editor_healthy(page: Page) -> None:
    expect(page.locator(".ql-toolbar")).to_have_count(1)
    expect(page.locator(".ql-container")).to_have_count(1)
    assert page.evaluate(_SNOW_LOADED) > 0, "quill.snow.css is not loaded/applied"
    svg_w = page.evaluate(
        """() => {
          const s = document.querySelector('.ql-toolbar svg');
          return s ? s.getBoundingClientRect().width : null;
        }"""
    )
    assert svg_w is not None and svg_w < 40, svg_w


@pytest.mark.django_db(transaction=True)
def test_add_editor_renders_with_snow_theme(page: Page, live_server, superuser, knowledge_index):
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/knowledge/add/")
    _assert_editor_healthy(page)


@pytest.mark.django_db(transaction=True)
def test_add_round_trips_body(page: Page, live_server, superuser, knowledge_index):
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/knowledge/add/")
    page.fill("#id_title", "E2E Knowledge Article")
    # Set the editor body via the DOM and submit in ONE synchronous step (see
    # test_edit_prefills_and_updates): closes the Quill MutationObserver revert race that flakes on
    # mobile webkit. Real keyboard input through the shared editor is covered by the competition tests.
    page.evaluate(
        """() => {
          document.querySelector('#quill-body .ql-editor').innerHTML = '<p>Body written in the browser</p>';
          document.getElementById('id_title').form.requestSubmit();
        }"""
    )
    page.wait_for_load_state("networkidle")

    art = KnowledgeArticle.objects.get(title="E2E Knowledge Article")
    assert "Body written in the browser" in art.body


@pytest.mark.django_db(transaction=True)
def test_add_strips_script_on_save(page: Page, live_server, superuser, knowledge_index):
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/knowledge/add/")
    page.fill("#id_title", "E2E KB XSS")
    page.evaluate(
        """() => {
          const ed = document.querySelector('#quill-body .ql-editor');
          ed.innerHTML = '<p>safe text</p><script>window.__x=1<\\/script>';
        }"""
    )
    page.eval_on_selector("#id_title", "el => el.form.requestSubmit()")
    page.wait_for_load_state("networkidle")

    art = KnowledgeArticle.objects.get(title="E2E KB XSS")
    assert "safe text" in art.body
    assert "<script" not in art.body.lower()


@pytest.mark.django_db(transaction=True)
def test_edit_prefills_and_updates(page: Page, live_server, superuser, knowledge_index):
    art = KnowledgeArticle.objects.create(
        title="Editable KB", locale="ru", body="<p>Existing <strong>body</strong></p>"
    )
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/knowledge/articles/{art.pk}/edit/")
    _assert_editor_healthy(page)
    expect(page.locator("#quill-body .ql-editor")).to_contain_text("Existing body")

    # Append through the editor DOM and submit in ONE synchronous step: the submit handler reads
    # quill.root.innerHTML synchronously during requestSubmit(), before Quill's async
    # MutationObserver can revert a raw DOM edit it doesn't track (that revert, when submit was a
    # separate call, is what flaked on mobile webkit). Keyboard input is covered by the competition tests.
    page.evaluate(
        """() => {
          document.querySelector('#quill-body .ql-editor').insertAdjacentHTML('beforeend', '<p>plus more</p>');
          document.getElementById('id_title').form.requestSubmit();
        }"""
    )
    page.wait_for_load_state("networkidle")

    art.refresh_from_db()
    assert "plus more" in art.body
    assert "Existing" in art.body  # the prefilled body survived the edit round-trip
