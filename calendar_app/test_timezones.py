"""An event's time zone comes from its place, a reader's from their browser (issue #344)."""

from zoneinfo import ZoneInfo

from django.test import TestCase

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
