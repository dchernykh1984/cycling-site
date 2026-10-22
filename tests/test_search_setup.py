"""What lets a search engine find the site and understand it.

The site was technically open to crawlers -- robots.txt allowed everything, the sitemap answered --
and still did not come up in Google. These pin down the pieces added for that: the ownership tags
the two consoles read, the home page saying whose site it is, every language of the section pages
in the sitemap, the calendar's own views in it, and a date on every event entry.
"""

import datetime
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from calendar_app.models import Competition
from cycling_site.jsonld import dumps


def _home(client, language="ru"):
    return client.get(f"/{language}/", HTTP_ACCEPT_LANGUAGE=language).content.decode()


def _json_ld(html):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    # Parsed as the browser hands it over: no character references decoded.
    return [json.loads(block) for block in blocks]


class VerificationTagTests(TestCase):
    @override_settings(GOOGLE_SITE_VERIFICATION="g-token-123", YANDEX_VERIFICATION="y-token-456")
    def test_the_consoles_find_their_tags_on_the_home_page(self):
        html = _home(self.client)
        self.assertIn('<meta name="google-site-verification" content="g-token-123" />', html)
        self.assertIn('<meta name="yandex-verification" content="y-token-456" />', html)

    @override_settings(GOOGLE_SITE_VERIFICATION="g-token-123")
    def test_the_tag_is_on_every_page_not_only_the_home_page(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertIn('name="google-site-verification"', html)

    @override_settings(GOOGLE_SITE_VERIFICATION="", YANDEX_VERIFICATION="")
    def test_unset_means_no_tag_at_all(self):
        html = _home(self.client)
        self.assertNotIn("site-verification", html)
        self.assertNotIn("yandex-verification", html)

    @override_settings(GOOGLE_SITE_VERIFICATION='x" /><script>alert(1)</script>')
    def test_a_value_cannot_inject_markup(self):
        self.assertNotIn("<script>alert(1)</script>", _home(self.client))


class HomeOrganizationTests(TestCase):
    def _graph(self, language="ru"):
        for block in _json_ld(_home(self.client, language)):
            if "@graph" in block:
                return {node["@type"]: node for node in block["@graph"]}
        self.fail("no organisation markup on the home page")

    def test_the_home_page_names_a_sports_organization_and_a_website(self):
        graph = self._graph()
        self.assertIn("SportsOrganization", graph)
        self.assertIn("WebSite", graph)

    @override_settings(
        ORGANIZATION_NAME="Universal Bicycle Team",
        ORGANIZATION_AREA="Almaty",
        ORGANIZATION_SAME_AS=["https://t.me/example", "javascript:alert(1)"],
    )
    def test_the_club_carries_what_the_settings_say_and_only_web_links(self):
        club = self._graph()["SportsOrganization"]
        self.assertEqual(club["name"], "Universal Bicycle Team")
        self.assertEqual(club["areaServed"]["name"], "Almaty")
        self.assertEqual(club["sameAs"], ["https://t.me/example"])

    @override_settings(ORGANIZATION_AREA="", ORGANIZATION_SAME_AS=[])
    def test_nothing_is_claimed_that_was_not_set(self):
        club = self._graph()["SportsOrganization"]
        self.assertNotIn("areaServed", club)
        self.assertNotIn("sameAs", club)

    def test_the_logo_is_an_absolute_address_of_a_file_that_exists(self):
        logo = self._graph()["SportsOrganization"]["logo"]
        self.assertTrue(logo.startswith("http"), logo)
        self.assertTrue((Path(settings.BASE_DIR) / "cycling_site/static/logo-512.png").is_file())

    def test_the_search_box_points_at_the_site_search(self):
        action = self._graph()["WebSite"]["potentialAction"]
        self.assertIn(f"{reverse('search')}?q={{search_term_string}}", action["target"]["urlTemplate"])

    def test_the_website_states_its_language(self):
        self.assertEqual(self._graph("kk")["WebSite"]["inLanguage"], "kk")


class JsonLdSerialisationTests(TestCase):
    def test_a_closing_script_tag_cannot_end_the_block_and_the_json_stays_valid(self):
        raw = dumps({"name": "Race </script><!-- & co"})
        self.assertNotIn("</script>", raw)
        self.assertNotIn("<!--", raw)
        self.assertEqual(json.loads(raw)["name"], "Race </script><!-- & co")

    def test_no_character_references_reach_the_block(self):
        self.assertNotIn("&quot;", dumps({"a": 'say "hi"'}))


class SitemapLanguagesTests(TestCase):
    def _section(self, name):
        response = self.client.get(reverse("sitemap_section", args=[name]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_home_page_is_listed_in_every_language(self):
        body = self._section("wagtail")
        for language in ("ru", "kk", "en"):
            self.assertRegex(body, rf"<loc>https?://[^<]+/{language}/</loc>")

    def test_each_entry_names_its_translations(self):
        body = self._section("wagtail")
        self.assertIn('hreflang="kk"', body)
        self.assertIn('hreflang="x-default"', body)

    def test_the_calendar_views_are_listed_in_every_language(self):
        body = self._section("sections")
        for language in ("ru", "kk", "en"):
            for path in ("calendar/", "calendar/list/", "calendar/map/"):
                self.assertIn(f"/{language}/{path}</loc>", body)

    def test_the_index_offers_the_new_section(self):
        self.assertIn("sitemap-sections.xml", self.client.get(reverse("sitemap")).content.decode())


class CompetitionLastmodTests(TestCase):
    def test_an_approved_event_carries_a_date(self):
        comp = Competition.objects.create(
            title_ru="Dated race",
            date_start=datetime.date.today() + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
            approved_at=timezone.make_aware(datetime.datetime(2026, 9, 1, 12, 0)),
        )
        body = self.client.get(reverse("sitemap_section", args=["competitions"])).content.decode()
        entry = body[body.index(comp.get_absolute_url()) :].split("</url>")[0]
        self.assertIn("<lastmod>2026-09-01", entry)

    def test_an_event_without_an_approval_date_is_still_listed(self):
        comp = Competition.objects.create(
            title_ru="Undated race",
            date_start=datetime.date.today() + datetime.timedelta(days=5),
            status=Competition.Status.APPROVED,
        )
        body = self.client.get(reverse("sitemap_section", args=["competitions"])).content.decode()
        self.assertIn(comp.get_absolute_url(), body)


class DefaultShareImageTests(TestCase):
    def test_the_file_is_the_size_the_page_declares(self):
        from PIL import Image

        with Image.open(Path(settings.BASE_DIR) / "cycling_site/static/og-default.png") as image:
            self.assertEqual(image.size, (1200, 630))
