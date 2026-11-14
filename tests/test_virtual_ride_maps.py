"""The virtual ride's maps: a city each, in a folder of the trainer's maps/ the page lists, and nothing but data."""

from numbers import Real

from django.test import SimpleTestCase

from tests import trainer_page
from trainer.models import VirtualRide

# The members' saved rides and group races keep the key of the route they were ridden on
RIDDEN = {"center", "medeu", "oldtown", "farabi"}
# What world.js draws along a route
SCENERIES = {"city", "gorge"}


def _listed() -> list[str]:
    return [path.parent.name for path in trainer_page.local_files() if path.parent.parent == trainer_page.MAPS]


def _routes():
    return [route for data in trainer_page.maps().values() for route in data.get("routes", [])]


class MapsTests(SimpleTestCase):
    def test_the_page_loads_every_map_folder_once(self):
        folders = sorted(path.name for path in trainer_page.MAPS.iterdir() if path.is_dir())
        self.assertTrue(folders)
        self.assertEqual(sorted(_listed()), folders)

    def test_a_map_is_named_after_its_folder(self):
        for folder, data in trainer_page.maps().items():
            self.assertEqual(data["id"], folder)

    def test_a_map_its_routes_and_its_sights_are_named_in_every_language(self):
        for folder, data in trainer_page.maps().items():
            names = [data["name"]]
            names += [route[key] for route in data.get("routes", []) for key in ("name", "desc")]
            names += [sight["name"] for sight in data.get("landmarks", [])]
            for name in names:
                self.assertEqual(set(name), {"ru", "kk", "en"}, folder)
                self.assertTrue(all(isinstance(text, str) and text.strip() for text in name.values()), name)

    def test_a_route_is_a_line_of_points_with_their_heights(self):
        routes = _routes()
        self.assertTrue(routes)
        for route in routes:
            self.assertGreaterEqual(len(route["pts"]), 2, route["id"])
            for point in route["pts"] + route.get("extend", []):
                self.assertEqual(len(point), 3, route["id"])
                lat, lon, _ = point
                self.assertTrue(all(isinstance(n, Real) for n in point), route["id"])
                self.assertTrue(-90 <= lat <= 90 and -180 <= lon <= 180, route["id"])
            self.assertIsInstance(route["loop"], bool)
            self.assertIn(route["scenery"], SCENERIES)
            self.assertTrue(route["width"] > 0 and route["lanes"] > 0, route["id"])

    def test_a_sight_stands_at_a_place(self):
        for folder, data in trainer_page.maps().items():
            for sight in data.get("landmarks", []):
                self.assertIsInstance(sight["type"], str, folder)
                self.assertTrue(-90 <= sight["lat"] <= 90 and -180 <= sight["lon"] <= 180, sight["type"])
                self.assertGreater(sight["r"], 0, sight["type"])

    def test_a_route_s_key_is_its_own_across_every_map_and_fits_the_site(self):
        keys = [route["id"] for route in _routes()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLessEqual(RIDDEN, set(keys), "a route already ridden lost its key, and its records with it")
        longest = VirtualRide._meta.get_field("route").max_length
        self.assertTrue(all(0 < len(key) <= longest for key in keys), keys)
