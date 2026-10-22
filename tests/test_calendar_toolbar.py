"""The period row above the calendar, the list and the map (_period_nav.html).

The arrows, Today, the kinds of period and the month picker are
our own; FullCalendar's toolbar is gone. Its bundle carries no Kazakh at all, so every label a reader
sees comes from our catalogue, and the tests assert against `gettext`, never against a pasted word.
"""

import datetime
import json
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from calendar_app.models import Competition
from calendar_app.views import calendar_year_choices
from locations.models import add_location_child
from tests.language_urls import in_language


def _json_script(html, element_id):
    """The data a page hands its script through Django's json_script."""
    block = re.search(rf'<script id="{element_id}" type="application/json">(.*?)</script>', html, flags=re.S)
    return json.loads(block.group(1)) if block else None


class TodayButtonTests(TestCase):
    def test_the_label_is_translated_in_every_locale(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                with translation.override(language):
                    today = translation.gettext("Today")
                response = self.client.get(in_language(reverse("calendar"), language))
                self.assertContains(response, f"data-period-today>{today}</button>")

    def test_the_label_starts_with_a_capital_letter(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language), translation.override(language):
                label = translation.gettext("Today")
                self.assertEqual(label[:1], label[:1].upper())

    def test_the_russian_and_kazakh_labels_are_not_the_english_source(self):
        """A missing or fuzzy catalogue entry silently serves the English string."""
        words = (
            "Today",
            "Today tomorrow",
            "Weekend",
            "Week",
            "Month",
            "whole year",
            "from %s",
            "Arrows: by day",
            "Arrows: by weekend",
            "Arrows: by week",
            "Arrows: by month",
            "Arrows: by year",
            "tap the month or year",
            "Remove filter",
        )
        for language in ("ru", "kk"):
            for word in words:
                with self.subTest(language=language, word=word), translation.override(language):
                    self.assertNotEqual(translation.gettext(word), word)


class MonthPickerTests(TestCase):
    """Jumping to a month directly, instead of walking there one click at a time."""

    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        cls.venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        cls.today = datetime.date.today()

    def _race(self, when, **kwargs):
        return Competition.objects.create(
            title_ru="Race",
            date_start=when,
            status=kwargs.pop("status", Competition.Status.APPROVED),
            location=self.venue,
            **kwargs,
        )

    def test_every_tab_offers_twelve_months_and_this_year(self):
        """The three tabs move through time alike (issue #330)."""
        for name in ("calendar", "calendar_list", "calendar_map"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertEqual([n for n, _ in _json_script(html, "period-months")], list(range(1, 13)))
                self.assertIn(self.today.year, _json_script(html, "period-years"))

    def test_the_months_are_named_in_the_readers_language(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                with translation.override(language):
                    expected = translation.gettext("January")
                if language != "en":
                    # A month name the catalogue never learned would come back as the source.
                    self.assertNotEqual(expected, "January")
                html = self.client.get(in_language(reverse("calendar"), language)).content.decode()
                self.assertEqual(_json_script(html, "period-months")[0], [1, expected])

    def test_the_years_reach_back_to_the_oldest_event(self):
        self._race(self.today - datetime.timedelta(days=365 * 6))
        oldest = self.today.year - 6
        years = calendar_year_choices()
        self.assertEqual(years[0], oldest)
        self.assertEqual(years[-1], self.today.year)
        self.assertEqual(years, list(range(oldest, self.today.year + 1)))

    def test_the_years_reach_forward_to_the_furthest_event(self):
        self._race(self.today + datetime.timedelta(days=365 * 2))
        self.assertEqual(calendar_year_choices()[-1], self.today.year + 2)

    def test_a_stage_race_ending_next_year_carries_its_year_in(self):
        self._race(datetime.date(self.today.year + 3, 12, 30), date_end=datetime.date(self.today.year + 4, 1, 2))
        self.assertIn(self.today.year + 4, calendar_year_choices())

    def test_an_empty_calendar_still_offers_this_year(self):
        self.assertEqual(calendar_year_choices(), [self.today.year])

    def test_events_nobody_can_see_do_not_stretch_the_list(self):
        """A hidden, deleted or unapproved event must not add a year with nothing to show in it."""
        self._race(self.today - datetime.timedelta(days=365 * 5), is_hidden=True)
        self._race(self.today - datetime.timedelta(days=365 * 7), is_deleted=True)
        self._race(self.today - datetime.timedelta(days=365 * 9), status=Competition.Status.PENDING_APPROVAL)
        self.assertEqual(calendar_year_choices(), [self.today.year])
