"""What lets a search engine find the site and understand it.

The site was technically open to crawlers -- robots.txt allowed everything, the sitemap answered --
and still did not come up in Google. These pin down the pieces added for that: the ownership tags
the two consoles read, the home page saying whose site it is, every language of the section pages
in the sitemap, the calendar's own views in it, and a date on every event entry.
"""

import json
import re

from django.test import TestCase

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
