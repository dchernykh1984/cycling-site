"""Knowledge and news pages, as a search result shows them.

Both carried the same site-wide description as the competitions did, so a search index had nothing
to tell one article from another -- only their titles differed.
"""

import re

from django.test import TestCase

from cycling_site.summaries import summarize
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle


def _description(html):
    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else None


class SummarizeTests(TestCase):
    def test_it_flattens_markup_to_prose(self):
        self.assertEqual(summarize("<p>Hello <b>there</b></p>"), "Hello there")

    def test_it_skips_an_empty_source_for_the_next_one(self):
        self.assertEqual(summarize("", "<p>Fallback</p>"), "Fallback")

    def test_an_inline_image_contributes_nothing(self):
        body = '<p><img src="data:image/png;base64,' + "A" * 5000 + '"> Real text</p>'
        self.assertEqual(summarize(body), "Real text")

    def test_it_cuts_on_a_word(self):
        text = summarize("<p>" + "word " * 200 + "</p>", limit=50)
        self.assertLessEqual(len(text), 50)
        self.assertTrue(text.endswith("..."))

    def test_nothing_to_say_stays_empty(self):
        self.assertEqual(summarize(None, "", "<p> </p>"), "")


class KnowledgeArticleMetaTests(TestCase):
    def test_the_description_comes_from_the_article(self):
        article = KnowledgeArticle.objects.create(
            title="Tyre pressure",
            slug="tyre-pressure",
            body="<p>How to pick a pressure for a gravel tyre without guessing.</p>",
        )
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertIn("gravel tyre", _description(html))

    def test_two_articles_do_not_share_a_description(self):
        first = KnowledgeArticle.objects.create(title="A", slug="a", body="<p>About chains.</p>")
        second = KnowledgeArticle.objects.create(title="B", slug="b", body="<p>About wheels.</p>")

        def described(article):
            return _description(self.client.get(article.get_absolute_url()).content.decode())

        self.assertNotEqual(described(first), described(second))


class NewsArticleMetaTests(TestCase):
    def test_the_intro_is_preferred_over_the_body(self):
        article = NewsArticle.objects.create(
            title_ru="Race report",
            slug="race-report",
            intro="A short lead for the report.",
            body="<p>Long body text.</p>",
        )
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertIn("short lead", _description(html))

    def test_the_body_is_used_when_there_is_no_intro(self):
        article = NewsArticle.objects.create(
            title_ru="Bodied", slug="bodied", intro="", body="<p>Body carries the story.</p>"
        )
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertIn("carries the story", _description(html))
