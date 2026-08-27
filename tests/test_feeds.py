"""RSS and Atom for news and for newly added events.

Both feeds are public addresses that change on their own, which is the point for a reader and for
a crawler alike -- so what must hold is that they parse, carry absolute links, and never leak an
article or an event that is not public.
"""

import datetime
from xml.etree import ElementTree

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from calendar_app.models import Competition
from locations.models import add_location_child
from news.models import NewsArticle

ATOM = "{http://www.w3.org/2005/Atom}"


def _parse(payload):
    """Parse a feed this site just produced -- not untrusted input, hence the plain parser."""
    return ElementTree.fromstring(payload)  # noqa: S314


class NewsFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.article = NewsArticle.objects.create(
            title_ru="Season opener",
            intro_ru="How the first race went.",
            body_ru="<p>A long report.</p>",
            published_at=now,
        )
        NewsArticle.objects.create(title_ru="Draft note", published_at=now, is_hidden=True)
        NewsArticle.objects.create(title_ru="Removed note", published_at=now, is_deleted=True)

    def test_the_rss_feed_parses_and_carries_the_article(self):
        response = self.client.get(reverse("news_rss"))
        self.assertEqual(response.status_code, 200)
        root = _parse(response.content)
        titles = [item.findtext("title") for item in root.iter("item")]
        self.assertIn("Season opener", titles)

    def test_the_atom_feed_parses_too(self):
        response = self.client.get(reverse("news_atom"))
        self.assertEqual(response.status_code, 200)
        root = _parse(response.content)
        titles = [entry.findtext(f"{ATOM}title") for entry in root.iter(f"{ATOM}entry")]
        self.assertIn("Season opener", titles)

    def test_an_item_links_to_the_article_in_full(self):
        root = _parse(self.client.get(reverse("news_rss")).content)
        link = next(item.findtext("link") for item in root.iter("item"))
        self.assertTrue(link.startswith("http"))
        self.assertIn(self.article.get_absolute_url(), link)

    def test_nothing_hidden_or_deleted_is_syndicated(self):
        body = self.client.get(reverse("news_rss")).content.decode()
        self.assertNotIn("Draft note", body)
        self.assertNotIn("Removed note", body)


class NewCompetitionsFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        now = timezone.now()
        today = datetime.date.today()
        cls.newest = Competition.objects.create(
            title_ru="Added yesterday",
            date_start=today + datetime.timedelta(days=40),
            status=Competition.Status.APPROVED,
            location=venue,
            approved_at=now,
        )
        cls.older = Competition.objects.create(
            title_ru="Added last month",
            date_start=today + datetime.timedelta(days=2),
            status=Competition.Status.APPROVED,
            location=venue,
            approved_at=now - datetime.timedelta(days=30),
        )
        Competition.objects.create(
            title_ru="Still waiting",
            date_start=today + datetime.timedelta(days=3),
            status=Competition.Status.PENDING_APPROVAL,
            location=venue,
        )
        cls.never_stamped = Competition.objects.create(
            title_ru="Approved long ago",
            date_start=today + datetime.timedelta(days=1),
            status=Competition.Status.APPROVED,
            location=venue,
            approved_at=None,
        )

    def test_the_newest_addition_comes_first(self):
        """The feed answers "what is new", so it is ordered by approval, not by race date."""
        root = _parse(self.client.get(reverse("calendar_rss")).content)
        titles = [item.findtext("title") for item in root.iter("item")]
        self.assertEqual(titles[:2], ["Added yesterday", "Added last month"])

    def test_an_event_with_no_approval_stamp_does_not_head_the_feed(self):
        """Postgres sorts NULLs first in a descending order, so it would come out on top."""
        root = _parse(self.client.get(reverse("calendar_rss")).content)
        titles = [item.findtext("title") for item in root.iter("item")]
        self.assertNotIn("Approved long ago", titles)

    def test_an_unapproved_event_never_appears(self):
        self.assertNotIn("Still waiting", self.client.get(reverse("calendar_rss")).content.decode())

    def test_the_atom_variant_is_served_as_atom(self):
        response = self.client.get(reverse("calendar_atom"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("atom", response["Content-Type"])


class FeedDiscoveryTests(TestCase):
    """A feed nobody can find is a feed nobody reads."""

    def test_every_page_declares_the_news_feeds(self):
        html = self.client.get(reverse("news_index")).content.decode()
        self.assertIn(f'href="{reverse("news_rss")}"', html)
        self.assertIn(f'href="{reverse("news_atom")}"', html)

    def test_the_calendar_declares_and_links_its_own(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertIn('type="text/calendar"', html)
        self.assertIn(f'href="{reverse("calendar_ics")}"', html)
        self.assertIn(f'href="{reverse("calendar_rss")}"', html)
