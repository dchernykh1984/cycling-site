"""Links an author wrote without a language get the reader's one as the page is drawn."""

import datetime

from django.test import TestCase
from django.utils import translation

from calendar_app.models import Competition
from home.templatetags.seo_tags import localized_links


class LocalizedLinksFilterTests(TestCase):
    def _in(self, language, html):
        with translation.override(language):
            return localized_links(html)

    def test_a_bare_site_path_gets_the_language(self):
        self.assertEqual(self._in("ru", '<a href="/calendar/719/">x</a>'), '<a href="/ru/calendar/719/">x</a>')
        self.assertEqual(
            self._in("kk", '<a href="/calendar/list/?location=2">x</a>'),
            '<a href="/kk/calendar/list/?location=2">x</a>',
        )
        self.assertEqual(self._in("en", '<a href="/">home</a>'), '<a href="/en/">home</a>')

    def test_what_already_has_a_language_or_needs_none_is_left_alone(self):
        for html in (
            '<a href="/kk/calendar/1/">x</a>',
            '<a href="/en/">x</a>',
            '<a href="/media/news/hero/a.jpg">x</a>',
            '<a href="/api/v1/competitions/">x</a>',
            '<a href="/sitemap.xml">x</a>',
            '<a href="https://example.com/calendar/1/">x</a>',
            '<a href="//cdn.example.com/x">x</a>',
            '<a href="#results">x</a>',
            '<a href="mailto:a@example.com">x</a>',
        ):
            with self.subTest(html=html):
                self.assertEqual(self._in("ru", html), html)


class LocalizedLinksOnPagesTests(TestCase):
    def test_an_event_description_links_in_the_page_language(self):
        comp = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 9, 1),
            status=Competition.Status.APPROVED,
            description_ru='<p><a href="/calendar/719/">schedule</a></p>',
            description_kk='<p><a href="/calendar/719/">schedule</a></p>',
        )
        self.assertContains(self.client.get(f"/ru/calendar/{comp.pk}/"), 'href="/ru/calendar/719/"')
        self.assertContains(self.client.get(f"/kk/calendar/{comp.pk}/"), 'href="/kk/calendar/719/"')
        comp.refresh_from_db()
        self.assertIn('href="/calendar/719/"', comp.description_ru)  # nothing stored changes
