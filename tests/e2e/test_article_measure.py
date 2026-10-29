"""A knowledge article or a news item reads at 45 to 75 characters a line on a desktop (#388)."""

import pytest
from playwright.sync_api import Page, expect

from knowledge.models import KnowledgeArticle, KnowledgeIndexPage

SENTENCE = (
    "The ride leaves the square at eight, climbs past the reservoir to the pass and comes back down "
    "the old road, with a stop for tea at the top where the group waits for everyone. "
)

# Characters on each line the browser drew of the article's first paragraph.
LINE_LENGTHS = """() => {
  const text = document.querySelector('.article-body p').firstChild;
  const range = document.createRange();
  const lines = new Map();
  for (let i = 0; i < text.length; i++) {
    range.setStart(text, i);
    range.setEnd(text, i + 1);
    const rect = range.getClientRects()[0];
    if (!rect) continue;
    const top = Math.round(rect.top);
    lines.set(top, (lines.get(top) || 0) + 1);
  }
  return [...lines.values()];
}"""


@pytest.fixture
def knowledge_index(db, wagtail_home_page):
    """A live KnowledgeIndexPage so an article's address resolves."""
    from wagtail.models import Page, Site

    site = Site.objects.filter(is_default_site=True).first()
    root = site.root_page if site else Page.objects.filter(depth=1).first()
    index = KnowledgeIndexPage(title="Knowledge Base", slug="knowledge-base")
    root.add_child(instance=index)
    index.save_revision().publish()
    return index


@pytest.mark.parametrize("width", [1280, 1920])
@pytest.mark.django_db(transaction=True)
def test_an_article_reads_at_45_to_75_characters_a_line(page: Page, live_server, knowledge_index, width):
    article = KnowledgeArticle.objects.create(title="Measure", locale="ru", body=f"<p>{SENTENCE * 6}</p>")
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server.url}{article.get_absolute_url()}")
    expect(page.locator(".article-body p")).to_have_count(1)
    lines = page.evaluate(LINE_LENGTHS)[:-1]  # the last line is as short as the paragraph leaves it
    assert len(lines) > 3, lines
    assert all(45 <= length <= 75 for length in lines), lines
