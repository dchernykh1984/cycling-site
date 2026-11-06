"""A knowledge article's contents lead to its sections, which stop below the sticky menu."""

import re

import pytest
from playwright.sync_api import Page, expect

from knowledge.models import KnowledgeArticle, KnowledgeIndexPage

PARAGRAPH = "<p>" + "A section that runs long enough for the page to scroll well past it. " * 12 + "</p>"


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


@pytest.mark.django_db(transaction=True)
def test_a_line_of_the_contents_brings_its_section_into_view_below_the_menu(page: Page, live_server, knowledge_index):
    sections = "".join(f"<h2>Part {n}</h2>{PARAGRAPH}<h3>Detail {n}</h3>{PARAGRAPH}" for n in range(1, 6))
    # Russian: its menu is the tallest, 180px in light and dark on a computer
    article = KnowledgeArticle.objects.create(
        title="Contents", locale="ru", body=f"<p>The lead.</p><p>[toc]</p>{sections}"
    )
    page.goto(f"{live_server.url}{article.get_absolute_url()}")
    contents = page.locator("nav.article-toc")
    expect(contents.get_by_role("link")).to_have_count(10)
    # every line is a row to tap: 44px on a phone, at least 24px under a mouse
    shortest = contents.evaluate(
        "nav => Math.min(...[...nav.querySelectorAll('a')].map(a => a.getBoundingClientRect().height))"
    )
    fine = page.evaluate("matchMedia('(hover: hover) and (pointer: fine)').matches")
    assert shortest >= (24 if fine else 44), shortest

    contents.get_by_role("link", name="Detail 4").click()
    expect(page).to_have_url(re.compile(r"#section-detail-4$"))
    heading = page.locator("#section-detail-4")
    expect(heading).to_be_in_viewport()
    _below_the_menu(page, heading)
    # opened at the anchor, from a link elsewhere, the page lands there too
    page.goto(f"{live_server.url}{article.get_absolute_url()}#section-part-5")
    heading = page.locator("#section-part-5")
    expect(heading).to_be_in_viewport()
    _below_the_menu(page, heading)


def _below_the_menu(page, heading):
    menu_bottom = page.locator("nav.navbar").evaluate("nav => nav.getBoundingClientRect().bottom")
    box = heading.bounding_box()
    assert box is not None
    assert box["y"] >= menu_bottom - 1, (box, menu_bottom)
