"""An event's time zone comes from its place, a reader's from their browser (issue #344)."""

import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase

from calendar_app.models import Competition
from locations.models import Location, timezone_of

TOKYO = ZoneInfo("Asia/Tokyo")


def _tree():
    """A country with a point, a region and a city without one, and a venue in Tokyo."""
    country = Location.add_root(name_ru="Japan", name_en="Japan", lat="35.689500", lng="139.691700")
    region = country.add_child(name_ru="Kanto", name_en="Kanto")
    city = region.add_child(name_ru="Tokyo", name_en="Tokyo")
    venue = city.add_child(name_ru="Park", name_en="Park", lat="35.689500", lng="139.691700")
    return country, region, city, venue


class TimezoneOfTests(TestCase):
    def test_a_place_with_coordinates_has_their_zone(self):
        *_, venue = _tree()
        self.assertEqual(timezone_of(venue), TOKYO)

    def test_a_place_without_coordinates_takes_the_nearest_ancestor_with_them(self):
        _, _, city, _ = _tree()
        bare = city.add_child(name_ru="Bare", name_en="Bare")
        with self.assertNumQueries(1):
            self.assertEqual(timezone_of(bare), TOKYO)

    def test_the_nearest_ancestor_wins_over_one_further_up(self):
        country = Location.add_root(name_ru="C", name_en="C", lat="51.507400", lng="-0.127800")
        city = country.add_child(name_ru="City", name_en="City", lat="35.689500", lng="139.691700")
        venue = city.add_child(name_ru="V", name_en="V")
        self.assertEqual(timezone_of(venue), TOKYO)

    def test_no_coordinates_anywhere_up_the_chain_is_utc(self):
        country = Location.add_root(name_ru="Nowhere", name_en="Nowhere")
        venue = country.add_child(name_ru="V", name_en="V")
        self.assertEqual(timezone_of(venue), ZoneInfo("UTC"))
        self.assertEqual(timezone_of(None), ZoneInfo("UTC"))

    def test_the_event_takes_the_zone_of_its_place(self):
        *_, venue = _tree()
        comp = Competition(title_ru="R", date_start=datetime.date(2026, 9, 1), location=venue)
        self.assertEqual(comp.timezone, TOKYO)


class RegistrationClosesByTheEventsDayTests(TestCase):
    def _open_without_deadline(self, location, now):
        comp = Competition.objects.create(
            title_ru="R",
            date_start=datetime.date(2026, 9, 1),
            status=Competition.Status.APPROVED,
            registration_enabled=True,
            location=location,
        )
        with mock.patch("django.utils.timezone.now", return_value=now):
            return comp.is_registration_open()

    def test_the_last_day_ends_at_midnight_at_the_place(self):
        *_, venue = _tree()
        # 16:00 UTC on the 1st is already 01:00 on the 2nd in Tokyo.
        late = datetime.datetime(2026, 9, 1, 16, 0, tzinfo=datetime.UTC)
        self.assertFalse(self._open_without_deadline(venue, late))
        self.assertTrue(self._open_without_deadline(venue, late - datetime.timedelta(hours=2)))

    def test_an_event_in_another_zone_is_still_on_its_last_day(self):
        nowhere = Location.add_root(name_ru="Nowhere", name_en="Nowhere")
        # 20:00 UTC on the 1st is the 2nd in the site's default zone, but still the 1st in UTC.
        self.assertTrue(self._open_without_deadline(nowhere, datetime.datetime(2026, 9, 1, 20, 0, tzinfo=datetime.UTC)))
