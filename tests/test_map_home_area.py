"""The map's home area: a region is a line in settings, not a value in the code (#330)."""

import json
import re

from django.test import TestCase, override_settings

from calendar_app.views import map_home_area
from locations.models import add_location_child

AREAS = {"almaty": ((43.05, 76.55), (43.90, 77.45)), "bishkek": ((42.70, 74.40), (43.00, 74.80))}


class MapDefaultViewTests(TestCase):
    @override_settings(MAP_DEFAULT_VIEW={"center": [0.0, 0.0], "zoom": 3})
    def test_the_map_receives_its_configured_fallback(self):
        response = self.client.get("/en/calendar/map/")
        match = re.search(
            r'<script id="map-default-view" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.S,
        )
        assert match is not None
        self.assertEqual(json.loads(match[1]), {"center": [0.0, 0.0], "zoom": 3})


@override_settings(MAP_HOME_AREAS=AREAS)
class MapHomeAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan", lat=48.1, lng=66.8)
        cls.almaty = add_location_child(cls.country, name="Almaty", name_ru="Almaty", lat=43.24, lng=76.95)
        cls.talgar = add_location_child(cls.country, name="Talgar", name_ru="Talgar", lat=43.30, lng=77.24)
        # Bishkek one level below its country, as Almaty is: the deepest chosen level is what counts.
        cls.kyrgyzstan = add_location_child(None, name="Kyrgyzstan", name_ru="Kyrgyzstan", lat=41.2, lng=74.7)
        cls.bishkek = add_location_child(cls.kyrgyzstan, name="Bishkek", name_ru="Bishkek", lat=42.87, lng=74.60)
        cls.nowhere = add_location_child(None, name="Unmapped", name_ru="Unmapped")

    def test_a_place_inside_an_area_opens_that_area(self):
        self.assertEqual(map_home_area({self.almaty.pk}), [[43.05, 76.55], [43.90, 77.45]])

    def test_every_place_inside_one_area_still_opens_it(self):
        self.assertEqual(map_home_area({self.almaty.pk, self.talgar.pk}), [[43.05, 76.55], [43.90, 77.45]])

    def test_another_configured_area_is_found_too(self):
        self.assertEqual(map_home_area({self.bishkek.pk}), [[42.70, 74.40], [43.00, 74.80]])

    def test_places_in_two_areas_fit_the_markers(self):
        self.assertIsNone(map_home_area({self.almaty.pk, self.bishkek.pk}))

    def test_a_country_and_a_city_in_it_open_the_citys_area(self):
        # The place filter keeps every ticked level; the deepest says where the reader is looking.
        self.assertEqual(map_home_area({self.country.pk, self.almaty.pk}), [[43.05, 76.55], [43.90, 77.45]])

    def test_a_whole_country_fits_the_markers(self):
        self.assertIsNone(map_home_area({self.country.pk}))

    def test_no_place_or_a_place_without_a_point_fits_the_markers(self):
        self.assertIsNone(map_home_area(set()))
        self.assertIsNone(map_home_area({self.nowhere.pk}))
