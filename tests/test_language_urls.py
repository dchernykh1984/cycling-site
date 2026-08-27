"""Each language as its own address.

The three languages used to share one path and be told apart by a cookie, so a crawler only ever
saw one of them: two thirds of the site did not exist as far as search was concerned. Now every
reader-facing page answers at /ru/..., /kk/... and /en/...; the bare path still works and
redirects to whichever one the reader asked for.
"""

import re

from django.test import TestCase
from django.urls import reverse
from django.utils import translation


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
