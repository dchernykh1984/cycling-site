"""The controls around the calendar grid.

FullCalendar draws its own toolbar and labels the buttons from its own bundle -- which spells
`today` in lower case and carries no Kazakh at all. The labels a reader sees have to come from
our catalogue instead, and the test asserts against `gettext`, never against a pasted word.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from calendar_app.models import Competition
from calendar_app.views import calendar_year_choices
from locations.models import add_location_child
from tests.language_urls import in_language


def _option_values(html, select_id):
    """The values a select offers, in the order the page lists them."""
    block = re.search(rf'<select id="{select_id}".*?</select>', html, flags=re.S)
    return re.findall(r'<option value="([^"]+)"', block.group(0)) if block else []


class TodayButtonTests(TestCase):
    def test_the_label_is_translated_in_every_locale(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                with translation.override(language):
                    expected = translation.gettext("Today")
                response = self.client.get(in_language(reverse("calendar"), language))
                self.assertContains(response, f"buttonText: {{ today: '{expected}' }}")

    def test_the_label_starts_with_a_capital_letter(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language), translation.override(language):
                label = translation.gettext("Today")
                self.assertEqual(label[:1], label[:1].upper())

    def test_the_russian_and_kazakh_labels_are_not_the_english_source(self):
        """A missing or fuzzy catalogue entry silently serves the English string."""
        for language in ("ru", "kk"):
            with self.subTest(language=language), translation.override(language):
                self.assertNotEqual(translation.gettext("Today"), "Today")


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

    def test_the_page_offers_twelve_months_and_a_year(self):
        response = self.client.get(reverse("calendar"))
        html = response.content.decode()
        self.assertEqual(_option_values(html, "calendar-month-select"), [str(n) for n in range(1, 13)])
        self.assertIn(str(self.today.year), _option_values(html, "calendar-year-select"))

    def test_the_months_are_named_in_the_readers_language(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                with translation.override(language):
                    expected = translation.gettext("January")
                response = self.client.get(in_language(reverse("calendar"), language))
                self.assertContains(response, f'<option value="1">{expected}</option>', html=True)

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
