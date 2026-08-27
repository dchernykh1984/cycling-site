"""What the sitemap must contain.

The site's own pages were never in it: `sitemap.xml` listed the knowledge base and a handful of
Wagtail pages, so 500+ competitions and every news article were content no search engine had been
told about. These tests pin the sections down, and pin down what must stay out of them -- a
pending, hidden or deleted event is not public, and offering it to a crawler would leak it.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from calendar_app.models import Competition
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle


def _competition(title="Race", **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": datetime.date.today() + datetime.timedelta(days=10),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


class SitemapIndexTests(TestCase):
    def test_the_index_lists_every_section(self):
        body = self.client.get(reverse("sitemap")).content.decode()
        for section in ("wagtail", "knowledge", "news", "competitions"):
            self.assertIn(f"sitemap-{section}.xml", body)

    def test_the_index_is_valid_xml_with_sitemap_entries(self):
        response = self.client.get(reverse("sitemap"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("<sitemapindex", response.content.decode())


class CompetitionSitemapTests(TestCase):
    def test_a_public_competition_is_listed(self):
        comp = _competition("Listed race")
        body = self.client.get(reverse("sitemap_section", args=["competitions"])).content.decode()
        self.assertIn(comp.get_absolute_url(), body)

    def test_a_past_competition_stays_listed(self):
        """A finished race is the page someone searching for last year's results wants."""
        comp = _competition("Old race", date_start=datetime.date(2023, 5, 1))
        body = self.client.get(reverse("sitemap_section", args=["competitions"])).content.decode()
        self.assertIn(comp.get_absolute_url(), body)

    def test_what_is_not_public_is_not_offered(self):
        hidden = _competition("Hidden", is_hidden=True)
        pending = _competition("Pending", status=Competition.Status.PENDING_APPROVAL)
        deleted = _competition("Deleted", is_deleted=True)
        body = self.client.get(reverse("sitemap_section", args=["competitions"])).content.decode()
        for comp in (hidden, pending, deleted):
            self.assertNotIn(comp.get_absolute_url(), body)


class NewsSitemapTests(TestCase):
    def test_a_visible_article_is_listed(self):
        article = NewsArticle.objects.create(title_ru="Announcement", slug="announcement")
        body = self.client.get(reverse("sitemap_section", args=["news"])).content.decode()
        self.assertIn(article.get_absolute_url(), body)

    def test_a_hidden_article_is_not(self):
        article = NewsArticle.objects.create(title_ru="Quiet", slug="quiet", is_hidden=True)
        body = self.client.get(reverse("sitemap_section", args=["news"])).content.decode()
        self.assertNotIn(article.get_absolute_url(), body)


class KnowledgeSitemapStillWorksTests(TestCase):
    def test_articles_are_still_listed_after_the_split(self):
        article = KnowledgeArticle.objects.create(title="Guide", slug="guide")
        body = self.client.get(reverse("sitemap_section", args=["knowledge"])).content.decode()
        self.assertIn(article.get_absolute_url(), body)
