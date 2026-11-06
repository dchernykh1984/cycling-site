"""Anchors on an article's headings, and the contents list a ``[toc]`` paragraph asks for.

Knowledge articles and news are drawn with an id on every h2 and h3, made of the heading's words, and a
paragraph holding ``[toc]`` alone becomes a list of links to them; nothing stored changes.
"""

import re

from django.test import SimpleTestCase, TestCase
from django.utils import translation

from cycling_site.contents import with_contents
from cycling_site.summaries import summarize
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle

BODY = (
    "<p>A lead before the contents.</p><p>[toc]</p>"
    "<h2>1. Finding an event</h2><p>Text.</p><h3>The calendar</h3><p>More.</p><h3>An event's page</h3>"
    "<h2>2. Participants</h2><p>Text.</p>"
)


def _ids(html):
    return re.findall(r'<h[23][^>]* id="([^"]+)"', html)


def _links(html):
    return re.findall(r'<a href="#([^"]+)">', html)


class ContentsTests(SimpleTestCase):
    def test_every_h2_and_h3_gets_an_id_made_of_its_words_the_same_on_every_visit(self):
        html = str(with_contents(BODY))
        self.assertEqual(
            _ids(html),
            ["section-1-finding-an-event", "section-the-calendar", "section-an-events-page", "section-2-participants"],
        )
        self.assertEqual(str(with_contents(BODY)), html)

    def test_a_heading_in_cyrillic_keeps_its_words_in_the_anchor(self):
        html = str(with_contents("<h2>2. \u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0443</h2>"))
        self.assertEqual(_ids(html), ["section-2-\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0443"])

    def test_headings_with_the_same_words_or_none_get_ids_of_their_own(self):
        html = str(with_contents("<h2>Photos</h2><h3>Photos</h3><h2>!!!</h2><h2>Photos</h2>"))
        self.assertEqual(_ids(html), ["section-photos", "section-photos-2", "section-3", "section-photos-3"])

    def test_the_marker_becomes_links_to_the_headings_h3_under_their_h2(self):
        html = str(with_contents(BODY))
        self.assertNotIn("[toc]", html)
        self.assertEqual(_links(html), _ids(html))
        contents = re.search(r'<nav class="article-toc".*?</nav>', html).group(0)
        # the h3 links sit in a list inside the first h2's item, the second h2 at the top level again
        self.assertRegex(contents, r"<li><a [^>]+>1\. Finding an event</a><ul><li><a [^>]+>The calendar</a></li>")
        self.assertIn('</ul></li><li><a href="#section-2-participants">2. Participants</a></li></ul>', contents)
        # it stands where the author put the marker: after the lead
        self.assertLess(html.index("A lead"), html.index("article-toc"))

    def test_without_the_marker_a_text_gets_anchors_and_nothing_else(self):
        html = str(with_contents("<h2>One</h2><p>[toc] inside a sentence stays.</p>"))
        self.assertNotIn("article-toc", html)
        self.assertIn("[toc] inside a sentence stays.", html)

    def test_a_marker_the_editor_aligned_still_draws_the_contents(self):
        html = str(with_contents('<p class="ql-align-center">[toc]</p><h2>One</h2>'))
        self.assertIn('<nav class="article-toc"', html)
        self.assertNotIn("[toc]", html)

    def test_a_second_marker_draws_no_second_contents(self):
        html = str(with_contents("<p>[toc]</p><h2>One</h2><p> [TOC] </p><h2>Two</h2>"))
        self.assertEqual(html.count('<nav class="article-toc"'), 1)
        self.assertNotIn("[TOC]", html)

    def test_a_headings_words_are_read_and_escaped_once_in_the_contents(self):
        html = str(with_contents("<p>[toc]</p><h2>Gear &amp; tools <strong>now</strong> &lt;b&gt;</h2>"))
        self.assertIn(">Gear &amp; tools now &lt;b&gt;</a>", html)
        self.assertNotIn("<b>", html)

    def test_what_a_heading_carries_stays_beside_its_new_id(self):
        html = str(with_contents('<h2 class="ql-align-center">Centred</h2>'))
        self.assertIn('<h2 class="ql-align-center" id="section-centred">Centred</h2>', html)

    def test_the_contents_are_titled_in_the_pages_language(self):
        with translation.override("ru"):
            html = str(with_contents("<p>[toc]</p><h2>One</h2>"))
        self.assertIn(">\u0421\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435</p>", html)

    def test_the_contents_of_a_text_in_another_language_are_titled_in_its_own(self):
        with translation.override("en"):
            html = str(with_contents("<p>[toc]</p><h2>One</h2>", "ru"))
        self.assertIn(">\u0421\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435</p>", html)

    def test_a_summary_never_reads_the_marker(self):
        self.assertEqual(summarize("<p>[toc]</p><p>The story begins.</p>"), "The story begins.")


class ArticlePagesTests(TestCase):
    def test_a_knowledge_article_and_a_news_item_are_drawn_with_anchors_and_their_contents(self):
        article = KnowledgeArticle.objects.create(title="Overview", slug="overview", locale="en", body=BODY)
        news = NewsArticle.objects.create(title_ru="News", slug="news-item", intro="Lead.", body=BODY)
        for url in (article.get_absolute_url(), news.get_absolute_url()):
            html = self.client.get(url).content.decode()
            self.assertIn('<nav class="article-toc" aria-labelledby="article-toc-title">', html)
            self.assertIn('id="section-2-participants"', html)
            self.assertIn('href="#section-2-participants"', html)
        # a Russian article opened at the English address keeps its contents' title in Russian
        russian = KnowledgeArticle.objects.create(title="Obzor", slug="obzor", locale="ru", body=BODY)
        html = self.client.get(russian.get_absolute_url().replace("/ru/", "/en/", 1)).content.decode()
        self.assertIn(">\u0421\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435</p>", html)
        # what is stored is what the author sent: the anchors are drawn, not saved
        article.refresh_from_db()
        self.assertIn("<p>[toc]</p>", article.body)
        self.assertNotIn("section-", article.body)
