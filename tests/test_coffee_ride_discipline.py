"""Coffee rides have a discipline of their own in the road direction; they used to land in its catch-all."""

from django.test import TestCase

from calendar_app.models import DisciplineCategory


class CoffeeRideTests(TestCase):
    def test_the_road_direction_offers_coffee_rides_just_before_its_catch_all(self):
        road = DisciplineCategory.objects.get(name_en="Road Cycling")
        names = list(road.disciplines.order_by("order").values_list("name_en", flat=True))
        self.assertEqual(names[-2:], ["Coffee Ride", "Other (Road Cycling)"])

    def test_it_is_named_in_every_language(self):
        ride = DisciplineCategory.objects.get(name_en="Road Cycling").disciplines.get(name_en="Coffee Ride")
        self.assertTrue(ride.name_ru and ride.name_kk)
        self.assertNotEqual(ride.name_ru, ride.name_en)
