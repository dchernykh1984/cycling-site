"""The location tree is fetched, not shipped inside the page.

Inlined, it was 1 021 380 bytes on `/calendar/` and `/calendar/list/` -- the two addresses that
get loaded and crawled most, and where that megabyte dominated the page weight.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from locations.models import add_location_child


class LocationPayloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty")
        add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")

    def test_the_calendar_pages_do_not_carry_the_tree(self):
        for name in ("calendar", "calendar_list"):
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotIn('id="locations-data"', html, name)
            self.assertIn(reverse("calendar_locations_json"), html, name)

    def test_the_endpoint_returns_the_nodes_the_cascade_needs(self):
        response = self.client.get(reverse("calendar_locations_json"))
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertTrue(rows)
        first = rows[0]
        for field in ("pk", "depth", "path", "name_ru", "name_kk", "name_en", "is_hidden", "lat", "lng"):
            self.assertIn(field, first)
        self.assertIn(self.city.pk, [row["pk"] for row in rows])

    def test_it_may_be_cached(self):
        """It is the same tree for everyone, and a few minutes stale costs nothing."""
        response = self.client.get(reverse("calendar_locations_json"))
        self.assertIn("max-age", response["Cache-Control"])


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class LocationPayloadCacheTests(TestCase):
    """The tree is the same megabyte for everyone; building it per visitor is waste.

    The suite runs on a dummy cache -- nothing is ever stored -- so this one class asks for a
    real one, which is what production has.
    """

    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        add_location_child(city, name="Republic Square", name_ru="Republic Square")

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)

    def test_a_second_request_does_not_query_for_the_tree_again(self):
        first = self.client.get(reverse("calendar_locations_json"))
        with self.assertNumQueries(0):
            second = self.client.get(reverse("calendar_locations_json"))
        self.assertEqual(first.content, second.content)

    def test_the_cached_copy_is_still_json_the_cascade_can_read(self):
        self.client.get(reverse("calendar_locations_json"))
        rows = self.client.get(reverse("calendar_locations_json")).json()
        self.assertTrue(all("path" in row for row in rows))
