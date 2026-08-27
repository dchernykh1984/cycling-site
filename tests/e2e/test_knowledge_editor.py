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
    page.goto(f"{live_server.url}/ru/knowledge/add/")
    _assert_editor_healthy(page)


@pytest.mark.django_db(transaction=True)
def test_add_round_trips_body(page: Page, live_server, superuser, knowledge_index):
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/knowledge/add/")
    page.fill("#id_title", "E2E Knowledge Article")
    expect(page.locator("#quill-body .ql-editor")).to_have_count(1)
    # Set the editor body via the DOM and submit in ONE synchronous step (see
    # test_edit_prefills_and_updates): closes the Quill MutationObserver revert race that flakes on
    # mobile webkit. Real keyboard input through the shared editor is covered by the competition tests.
    page.evaluate(
        """() => {
          document.querySelector('#quill-body .ql-editor').innerHTML = '<p>Body written in the browser</p>';
          document.getElementById('id_title').form.requestSubmit();
        }"""
    )
    # Wait for the post-save redirect (networkidle can settle before the POST round-trips on CI).
    page.wait_for_url(lambda url: "/ru/knowledge/add/" not in url)

    art = KnowledgeArticle.objects.get(title="E2E Knowledge Article")
    assert "Body written in the browser" in art.body


@pytest.mark.django_db(transaction=True)
def test_add_strips_script_on_save(page: Page, live_server, superuser, knowledge_index):
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/knowledge/add/")
    page.fill("#id_title", "E2E KB XSS")
    expect(page.locator("#quill-body .ql-editor")).to_have_count(1)
    # Set the script markup and submit in ONE synchronous step: the submit handler copies
    # quill.root.innerHTML before Quill's async MutationObserver reverts the raw DOM edit (a
    # separate submit call races it and flakes on mobile webkit); the server strips the script.
    page.evaluate(
        """() => {
          document.querySelector('#quill-body .ql-editor').innerHTML =
            '<p>safe text</p><script>window.__x=1<\\/script>';
          document.getElementById('id_title').form.requestSubmit();
        }"""
    )
    # Wait for the post-save redirect (networkidle can settle before the POST round-trips on CI).
    page.wait_for_url(lambda url: "/ru/knowledge/add/" not in url)

    art = KnowledgeArticle.objects.get(title="E2E KB XSS")
    assert "safe text" in art.body
    assert "<script" not in art.body.lower()


@pytest.mark.django_db(transaction=True)
def test_edit_prefills_and_updates(page: Page, live_server, superuser, knowledge_index):
    art = KnowledgeArticle.objects.create(
        title="Editable KB", locale="ru", body="<p>Existing <strong>body</strong></p>"
    )
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/knowledge/articles/{art.pk}/edit/")
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
    # Wait for the post-save redirect (networkidle can settle before the POST round-trips on CI).
    page.wait_for_url(lambda url: "/edit/" not in url)

    art.refresh_from_db()
    assert "plus more" in art.body
    assert "Existing" in art.body  # the prefilled body survived the edit round-trip


# A 1x1 transparent PNG as a base64 data URI -- a valid raster src the sanitizer accepts.
_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.mark.django_db(transaction=True)
def test_editor_exposes_richtext_tools(page: Page, live_server, superuser, knowledge_index):
    """The enriched toolbar (colour/align/indent) renders and blot-formatter is loaded."""
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/knowledge/add/")
    _assert_editor_healthy(page)
    # Quill renders each colour/align picker as both a hidden <select> and a picker <span> (so
    # the class resolves to 2 nodes); assert the control exists rather than an exact count.
    assert page.locator(".ql-toolbar .ql-color").count() >= 1
    assert page.locator(".ql-toolbar .ql-background").count() >= 1
    assert page.locator(".ql-toolbar .ql-align").count() >= 1
    expect(page.locator('.ql-toolbar button.ql-indent[value="+1"]')).to_have_count(1)
    # The vendored image-resize module is present and registered (offline, no CDN).
    assert page.evaluate("() => !!(window.QuillBlotFormatter && window.QuillBlotFormatter.default)")


@pytest.mark.django_db(transaction=True)
def test_image_size_and_float_survive_edit_round_trip(page: Page, live_server, superuser, knowledge_index):
    """A resized, left-floated image loads into the editor and re-saves with its geometry intact.

    Exercises both halves: the custom image blot keeps width/float/data-align through Quill's
    load + observer, and the server sanitizer keeps them on save.
    """
    body = (
        f'<p>Text <img src="{_PNG}" width="120" height="80" data-align="left" '
        'style="float: left; margin: 0px 1em 1em 0px;"> wraps to the right.</p>'
    )
    art = KnowledgeArticle.objects.create(title="KB Image", locale="ru", body=body)
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/knowledge/articles/{art.pk}/edit/")
    _assert_editor_healthy(page)
    expect(page.locator("#quill-body .ql-editor img")).to_have_count(1)
    # Re-submit unchanged; the sized/floated image must round-trip.
    page.evaluate("() => document.getElementById('id_title').form.requestSubmit()")
    page.wait_for_url(lambda url: "/edit/" not in url)

    art.refresh_from_db()
    assert 'width="120"' in art.body
    assert "float: left" in art.body
    assert 'data-align="left"' in art.body


@pytest.mark.django_db(transaction=True)
def test_text_color_and_alignment_saved(page: Page, live_server, superuser, knowledge_index):
    """Toolbar colour + block alignment survive the save-time sanitizer end to end."""
    inject_session(page, live_server, superuser)
    page.goto(f"{live_server.url}/ru/knowledge/add/")
    page.fill("#id_title", "KB Colored")
    expect(page.locator("#quill-body .ql-editor")).to_have_count(1)
    # Set the markup and submit synchronously (same MutationObserver race as the tests above).
    page.evaluate(
        """() => {
          document.querySelector('#quill-body .ql-editor').innerHTML =
            '<p class="ql-align-center">Centered</p>' +
            '<p><span style="color: rgb(230, 0, 0);">Red</span></p>';
          document.getElementById('id_title').form.requestSubmit();
        }"""
    )
    page.wait_for_url(lambda url: "/ru/knowledge/add/" not in url)

    art = KnowledgeArticle.objects.get(title="KB Colored")
    assert "ql-align-center" in art.body
    assert "color: rgb(230, 0, 0)" in art.body


@pytest.mark.django_db(transaction=True)
def test_floated_image_list_wraps_without_overlap_or_gap(page: Page, live_server, superuser, knowledge_index):
    """A list beside a left-floated image keeps its markers off the image *and* still reflows to
    full width once the image ends -- neither markers painted on the image (the outside-marker
    bug) nor an empty gap under it ("chin", which display:flow-root would leave).
    """
    # Inline height makes the 1x1 PNG a float the first items sit beside and the last flows under.
    items = "".join(
        f"<li>Install step {i} with enough text to wrap onto more than one line beside the "
        "floated image on the right of the column.</li>"
        for i in range(1, 6)
    )
    body = (
        f'<p><img src="{_PNG}" style="float: left; width: 50%; height: 220px; margin: 0 1rem 0.5rem 0;">'
        f" Intro line beside the image.</p><ol>{items}</ol>"
    )
    art = KnowledgeArticle.objects.create(title="KB Float List", locale="ru", body=body)
    page.goto(f"{live_server.url}{art.get_absolute_url()}")
    expect(page.locator(".article-body ol")).to_have_count(1)
    result = page.evaluate(
        """() => {
          const img = document.querySelector('.article-body img').getBoundingClientRect();
          const ol = document.querySelector('.article-body ol');
          const lis = [...ol.querySelectorAll('li')];
          const r = document.createRange(); r.selectNodeContents(lis[lis.length - 1]);
          const rects = [...r.getClientRects()];
          return {
            list_style_position: getComputedStyle(ol).listStylePosition,
            reflows_below_image: rects.some(rc => rc.top >= img.bottom - 2 && rc.left < img.right - 20),
          };
        }"""
    )
    # Markers ride in the text flow beside the image, never painted on top of it.
    assert result["list_style_position"] == "inside"
    # And the list flows back to full width under the image -- no empty gap beside it.
    assert result["reflows_below_image"] is True
