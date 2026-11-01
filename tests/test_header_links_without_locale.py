"""The header's page links when Wagtail has no locale row for the language (#385).

``Locale.get_active()`` falls back to the default language's row and raises when that is missing too.
A test database flushed between tests can be in that state; the header must then lose a link, not
answer every page with a 500.
"""

from unittest import mock

from django.test import TestCase
from wagtail.models import Locale

from home.templatetags.home_tags import get_about_url
from knowledge.templatetags.knowledge_tags import get_knowledge_index_url
from locations.templatetags.locations_tags import get_locations_map_url


class HeaderLinksWithoutALocaleTests(TestCase):
    def test_every_header_link_survives_a_missing_locale(self):
        with mock.patch.object(Locale, "get_active", side_effect=Locale.DoesNotExist):
            for tag in (get_locations_map_url, get_about_url, get_knowledge_index_url):
                with self.subTest(tag=tag.__name__):
                    tag()
