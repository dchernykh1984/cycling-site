"""What lets a search engine find the site and understand it.

The site was technically open to crawlers -- robots.txt allowed everything, the sitemap answered --
and still did not come up in Google. These pin down the pieces added for that: the ownership tags
the two consoles read, the home page saying whose site it is, every language of the section pages
in the sitemap, the calendar's own views in it, and a date on every event entry.
"""

import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from cycling_site.jsonld import dumps


def _home(client, language="ru"):
    return client.get(f"/{language}/", HTTP_ACCEPT_LANGUAGE=language).content.decode()


def _json_ld(html):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    # Parsed as the browser hands it over: no character references decoded.
    return [json.loads(block) for block in blocks]


class JsonLdSerialisationTests(TestCase):
    def test_a_closing_script_tag_cannot_end_the_block_and_the_json_stays_valid(self):
        raw = dumps({"name": "Race </script><!-- & co"})
        self.assertNotIn("</script>", raw)
        self.assertNotIn("<!--", raw)
        self.assertEqual(json.loads(raw)["name"], "Race </script><!-- & co")

    def test_no_character_references_reach_the_block(self):
        self.assertNotIn("&quot;", dumps({"a": 'say "hi"'}))


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
