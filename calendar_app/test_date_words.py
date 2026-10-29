"""An event's days in words, as the period line names them (#388, the interface skill's rule 12)."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from calendar_app.models import Competition
from calendar_app.views import date_range_words
from locations.models import add_location_child
from tests.language_urls import in_language

D = datetime.date
DASH = "\N{EN DASH}"
# The month names a date takes, spelled in escapes because the sources are ASCII-only:
# "oktyabrya", "sentyabrya" (Russian, genitive); "qazan", "zheltoqsan", "qantar" (Kazakh).
OCTOBER_RU = "\u043e\u043a\u0442\u044f\u0431\u0440\u044f"
SEPTEMBER_RU = "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f"
OCTOBER_KK = "\u049b\u0430\u0437\u0430\u043d"
DECEMBER_KK = "\u0436\u0435\u043b\u0442\u043e\u049b\u0441\u0430\u043d"
JANUARY_KK = "\u049b\u0430\u04a3\u0442\u0430\u0440"


def _words(language, start, end=None):
    with translation.override(language):
        return date_range_words(start, end)


class DateRangeWordsTests(TestCase):
    def test_a_day_a_range_a_turn_of_the_month_and_of_the_year(self):
        self.assertEqual(_words("en", D(2026, 10, 24)), "24 October 2026")
        self.assertEqual(_words("en", D(2026, 10, 24), D(2026, 10, 24)), "24 October 2026")
        self.assertEqual(_words("en", D(2026, 10, 24), D(2026, 10, 25)), f"24{DASH}25 October 2026")
        self.assertEqual(_words("en", D(2026, 9, 30), D(2026, 10, 2)), f"30 September {DASH} 2 October 2026")
        self.assertEqual(_words("en", D(2026, 12, 30), D(2027, 1, 2)), f"30 December 2026 {DASH} 2 January 2027")

    def test_russian_gives_the_month_the_case_a_date_takes(self):
        self.assertEqual(_words("ru", D(2026, 10, 24)), f"24 {OCTOBER_RU} 2026")
        self.assertEqual(_words("ru", D(2026, 9, 30), D(2026, 10, 2)), f"30 {SEPTEMBER_RU} {DASH} 2 {OCTOBER_RU} 2026")

    def test_kazakh_puts_the_year_first(self):
        self.assertEqual(_words("kk", D(2026, 10, 24), D(2026, 10, 25)), f"2026 24{DASH}25 {OCTOBER_KK}")
        self.assertEqual(
            _words("kk", D(2026, 12, 30), D(2027, 1, 2)), f"2026 30 {DECEMBER_KK} {DASH} 2027 2 {JANUARY_KK}"
        )


class EventDaysInWordsOnThePageTests(TestCase):
    """The list's table and the map's popups say the days as the period line does, not 14.03.2027."""

    RANGE = "date_from=2027-03-01&date_to=2027-03-31"

    @classmethod
    def setUpTestData(cls):
        # A made-up place in the South Atlantic: the test database carries the seeded real geography.
        country = add_location_child(None, name="Testland", name_ru="Testland", lat="-40.0", lng="-20.0")
        region = add_location_child(country, name="North", name_ru="North", lat="-40.0", lng="-20.0")
        city = add_location_child(region, name="Northville", name_ru="Northville", lat="-40.0", lng="-20.0")
        venue = add_location_child(city, name="Quay", name_ru="Quay", lat="-40.0", lng="-20.0")
        Competition.objects.create(
            title_ru="Spring Race",
            date_start=D(2027, 3, 14),
            date_end=D(2027, 3, 15),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def test_the_lists_table_names_the_days_in_words(self):
        body = self.client.get(f"{in_language(reverse('calendar_list'), 'en')}?{self.RANGE}").content.decode()
        self.assertIn(f"14{DASH}15 March 2027", body)
        self.assertNotIn("14.03.2027", body)

    def test_the_maps_popup_gets_the_days_in_words(self):
        response = self.client.get(f"{in_language(reverse('calendar_map_api'), 'en')}?{self.RANGE}")
        (place,) = response.json()
        self.assertEqual(place["competitions"][0]["when"], f"14{DASH}15 March 2027")
