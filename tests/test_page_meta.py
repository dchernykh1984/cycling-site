"""The head of every page, as a crawler reads it.

Before this, all 500+ competition pages carried the same description -- "Cycling events, news and
knowledge base" -- and no canonical at all, so nothing distinguished one event from another in a
search index. The title was also rendered across several template lines, which Django keeps, so it
began with blank lines.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from calendar_app.models import Competition

DEFAULT_DESCRIPTION = (
    "Calendar of endurance sport events -- cycling, running, cross-country skiing -- in "
    "Kazakhstan, Kyrgyzstan, Russia and beyond. Announcements, results and a knowledge base."
)


def _competition(title="Race", **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": datetime.date.today() + datetime.timedelta(days=10),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _meta(html, name):
    m = re.search(rf'<meta[^>]+name="{name}"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else None


def _prop(html, prop):
    m = re.search(rf'<meta[^>]+property="{prop}"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else None


class TitleShapeTests(TestCase):
    def test_the_title_has_no_stray_whitespace(self):
        comp = _competition("Tidy title race")
        html = self.client.get(comp.get_absolute_url()).content.decode()
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        self.assertEqual(title, title.strip())
        self.assertNotIn("\n", title)


class CanonicalTests(TestCase):
    def test_every_page_declares_a_canonical_address(self):
        comp = _competition("Canonical race")
        html = self.client.get(comp.get_absolute_url()).content.decode()
        m = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]*)"', html)
        self.assertIsNotNone(m)
        self.assertTrue(m.group(1).endswith(comp.get_absolute_url()))


class DefaultDescriptionTests(TestCase):
    def test_the_fallback_names_more_than_cycling(self):
        """The old default said "cycling" only, on a site that also lists running and skiing."""
        page = self.client.get(reverse("calendar"), HTTP_ACCEPT_LANGUAGE="en")
        description = _meta(page.content.decode(), "description")
        self.assertIsNotNone(description)
        lowered = description.lower()
        for word in ("running", "skiing", "kazakhstan"):
            self.assertIn(word, lowered)

    def test_the_fallback_is_translated(self):
        """A string left untranslated -- or marked fuzzy, which gettext ignores -- reads as English."""
        for language in ("ru", "kk"):
            with self.subTest(language=language), translation_override(language):
                expected = gettext(DEFAULT_DESCRIPTION)
                self.assertNotEqual(expected, DEFAULT_DESCRIPTION)
                html = self.client.get(reverse("calendar"), HTTP_ACCEPT_LANGUAGE=language).content.decode()
                self.assertIn(escape(expected), html)

    def test_the_same_text_is_used_for_sharing(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertEqual(_meta(html, "description"), _prop(html, "og:description"))


class SocialTagsTests(TestCase):
    def test_a_page_carries_an_image_and_a_card_type(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertTrue((_prop(html, "og:image") or "").endswith(".png"))
        self.assertEqual(_meta(html, "twitter:card"), "summary")


class CompetitionMetaTests(TestCase):
    """An event page has to say what it is: 500+ of them shared one description before."""

    def setUp(self):
        self.comp = _competition("Almaty Gran Fondo", date_start=datetime.date(2026, 10, 4))

    def _html(self):
        return self.client.get(self.comp.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()

    def test_the_title_is_the_event_name(self):
        self.assertIn("Almaty Gran Fondo", re.search(r"<title>(.*?)</title>", self._html()).group(1))

    def test_the_description_carries_the_name_and_the_date(self):
        description = _meta(self._html(), "description")
        self.assertIn("Almaty Gran Fondo", description)
        self.assertIn("2026", description)

    def test_two_events_do_not_share_a_description(self):
        other = _competition("Astana Night Run", date_start=datetime.date(2026, 5, 1))
        mine = _meta(self._html(), "description")
        theirs = _meta(self.client.get(other.get_absolute_url()).content.decode(), "description")
        self.assertNotEqual(mine, theirs)

    def test_the_description_names_the_place_when_there_is_one(self):
        from locations.models import Location, add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan", name_en="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty", name_en="Almaty")
        venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        self.comp.location = venue
        self.comp.save()
        self.assertIn("Almaty", _meta(self._html(), "description"))
        self.assertIsInstance(venue, Location)
