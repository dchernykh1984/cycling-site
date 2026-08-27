"""Each language as its own address.

The three languages used to share one path and be told apart by a cookie, so a crawler only ever
saw one of them: two thirds of the site did not exist as far as search was concerned. Now every
reader-facing page answers at /ru/..., /kk/... and /en/..., each self-canonical and each pointing
at the other two; the bare path still works and redirects to whichever one the reader asked for.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from calendar_app.models import Competition
from locations.models import add_location_child


def _alternates(html):
    return dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', html))


class PrefixedAddressTests(TestCase):
    def test_a_page_answers_at_each_language(self):
        for code in ("ru", "kk", "en"):
            with self.subTest(language=code):
                response = self.client.get(f"/{code}/calendar/list/")
                self.assertEqual(response.status_code, 200)
                self.assertIn(f'lang="{code}"', response.content.decode())

    def test_the_prefix_beats_the_accept_language_header(self):
        """Otherwise the same address would return different languages to different readers,
        which is the ambiguity the prefixes exist to remove."""
        html = self.client.get("/en/calendar/list/", HTTP_ACCEPT_LANGUAGE="ru").content.decode()
        self.assertIn('lang="en"', html)

    def test_a_bare_address_is_redirected_to_a_language(self):
        response = self.client.get("/calendar/list/", HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/en/calendar/list/")

    def test_a_bare_address_keeps_its_query_string(self):
        """Every link ever shared has to keep working, filters and all."""
        response = self.client.get("/calendar/list/?location=7", HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(response["Location"], "/ru/calendar/list/?location=7")

    def test_machine_addresses_carry_no_language(self):
        for path in ("/sitemap.xml", "/robots.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_a_missing_api_address_is_not_answered_with_a_redirect(self):
        """A client asking for something that does not exist gets 404, not a tour of the site."""
        self.assertEqual(self.client.get("/api/v1/no-such-endpoint/").status_code, 404)

    def test_reversing_follows_the_active_language(self):
        with translation.override("kk"):
            self.assertEqual(reverse("calendar_list"), "/kk/calendar/list/")


class HreflangTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        cls.competition = Competition.objects.create(
            title_ru="Spring race",
            date_start=datetime.date.today() + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def _page(self, language):
        url = f"/{language}" + reverse("competition_detail", args=[self.competition.pk])[3:]
        return self.client.get(url).content.decode()

    def test_every_language_is_declared(self):
        alternates = _alternates(self._page("ru"))
        for code in ("ru", "kk", "en"):
            self.assertIn(code, alternates)
            self.assertIn(f"/{code}/calendar/{self.competition.pk}/", alternates[code])

    def test_there_is_a_default_for_a_reader_we_cannot_place(self):
        self.assertIn("x-default", _alternates(self._page("en")))

    def test_each_language_is_canonical_to_itself(self):
        """Three addresses that all name one canonical would be three copies of one page."""
        for code in ("ru", "kk", "en"):
            with self.subTest(language=code):
                canonical = re.search(r'<link rel="canonical" href="([^"]+)"', self._page(code)).group(1)
                self.assertIn(f"/{code}/calendar/{self.competition.pk}/", canonical)

    def test_the_alternates_are_absolute(self):
        for url in _alternates(self._page("ru")).values():
            self.assertTrue(url.startswith("http"), url)


class SitemapLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        Competition.objects.create(
            title_ru="Spring race",
            date_start=datetime.date.today() + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def test_the_competition_section_lists_every_language(self):
        body = self.client.get("/sitemap-competitions.xml").content.decode()
        for code in ("ru", "kk", "en"):
            self.assertIn(f"/{code}/calendar/", body)

    def test_each_entry_points_at_its_translations(self):
        body = self.client.get("/sitemap-competitions.xml").content.decode()
        self.assertIn('hreflang="kk"', body)
        self.assertIn('hreflang="x-default"', body)


class InternalLinkTests(TestCase):
    """Links the site writes for itself should land on a page, not on a redirect to one."""

    def test_the_brand_links_to_the_home_page_in_the_current_language(self):
        html = self.client.get("/en/calendar/list/").content.decode()
        self.assertIn('class="navbar-brand fw-bold" href="/en/"', html)

    def test_no_navigation_link_needs_a_redirect(self):
        html = self.client.get("/kk/calendar/list/").content.decode()
        nav = html.split("<nav")[1].split("</nav>")[0]
        for href in re.findall(r'href="(/[^"]*)"', nav):
            if href.startswith(("/static/", "/media/", "/i18n/")):
                continue
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200, href)
