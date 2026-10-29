"""The place the model names, found among the places the page offers."""

from django.test import TestCase

from assistant import places
from assistant.tests.helpers import city, user, venue
from calendar_app.views import _get_locations_data


class PlaceTests(TestCase):
    def setUp(self):
        self.town = city()
        self.shop = venue(self.town)
        self.catch_all = self.town.get_children().get(is_hidden=True)
        self.rows = _get_locations_data(user())

    def _resolve(self, point=None, **place):
        return places.resolve({"country": "Testland", "city": "Testville", **place}, self.rows, point)

    def test_the_tree_holds_each_venue_under_its_city(self):
        country = next(node for node in places.tree(self.rows) if node["name"]["en"] == "Testland")
        (region,) = country["children"]
        (town,) = region["children"]
        self.assertEqual(town["id"], self.town.pk)
        self.assertEqual({child["id"] for child in town["children"]}, {self.shop.pk, self.catch_all.pk})

    def test_a_venue_written_another_way_is_the_one_the_site_has(self):
        found = self._resolve(venue={"ru": "", "kk": "", "en": "giant shop - Abay 47"})
        self.assertEqual(found.location, self.shop.pk)

    def test_a_city_without_a_spot_takes_its_catch_all(self):
        self.assertEqual(self._resolve(venue={"ru": "", "kk": "", "en": ""}).location, self.catch_all.pk)
        self.assertEqual(self._resolve().location, self.catch_all.pk)

    def test_a_spot_the_site_lacks_becomes_a_new_venue_with_the_tracks_point(self):
        found = self._resolve((43.25, 76.95), venue={"ru": "Vkhod v park", "kk": "", "en": "Park entrance"})
        self.assertIsNone(found.location)
        self.assertEqual(
            found.new_venue,
            {
                "city": self.town.pk,
                "name_ru": "Vkhod v park",
                "name_kk": "",
                "name_en": "Park entrance",
                "lat": 43.25,
                "lng": 76.95,
            },
        )

    def test_a_namesake_far_from_the_track_is_another_place(self):
        found = self._resolve((43.35, 76.95), venue={"ru": "", "kk": "", "en": "Giant shop, Abay 47"})
        self.assertIsNone(found.location)
        self.assertEqual(found.new_venue["name_ru"], "Giant shop, Abay 47")

    def test_a_city_the_site_lacks_is_named_back(self):
        found = self._resolve(city="Nowhereville")
        self.assertEqual((found.location, found.new_venue, found.missing_city), (None, None, "Nowhereville"))

    def test_no_city_means_nothing_yet(self):
        found = places.resolve({"venue": {"en": "Giant shop, Abay 47"}}, self.rows, None)
        self.assertEqual((found.location, found.new_venue, found.missing_city), (None, None, ""))
