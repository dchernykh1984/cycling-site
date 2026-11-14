"""The virtual ride's maps -- a city each, in a folder of the trainer's maps/, nothing but data -- and the objects
their sights are built from, a file each in objects/, shared by every map. The page lists them all."""

import math
import re
from numbers import Real

from django.test import SimpleTestCase

from tests import trainer_page
from trainer.models import VirtualRide

# The members' saved rides and group races keep the key of the route they were ridden on
RIDDEN = {"center", "medeu", "oldtown", "farabi"}
# What world.js draws along a route
SCENERIES = {"city", "gorge"}
OBJECTS = trainer_page.PAGE.parent / "alatau" / "objects"


def _listed() -> list[str]:
    return [path.parent.name for path in trainer_page.local_files() if path.parent.parent == trainer_page.MAPS]


def _km(origin: dict, point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (origin["lat"], origin["lon"], point[0], point[1]))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


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

    def test_a_map_with_routes_is_laid_out_from_a_point_among_them(self):
        for folder, data in trainer_page.maps().items():
            if not data.get("routes"):
                continue
            origin = data["origin"]
            points = [p for route in data["routes"] for p in route["pts"] + route.get("extend", [])]
            points += [(sight["lat"], sight["lon"]) for sight in data.get("landmarks", [])]
            # the scene is flat: some 50 km from its origin a map's east-west metres are half a per cent off
            self.assertLess(max(_km(origin, point) for point in points), 50, folder)

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


class ObjectsTests(SimpleTestCase):
    def test_the_page_loads_every_object_file_once_after_the_registry(self):
        files = trainer_page.local_files()
        listed = [path for path in files if path.parent == OBJECTS]
        self.assertEqual(sorted(path.name for path in listed), sorted(path.name for path in OBJECTS.glob("*.js")))
        registry = files.index(trainer_page.PAGE.parent / "alatau/js/landmarks.js")
        self.assertTrue(all(files.index(path) > registry for path in listed))

    def test_an_object_file_adds_the_one_object_it_is_named_after(self):
        for path in OBJECTS.glob("*.js"):
            added = re.findall(r"^addObject\('([\w-]+)', ", path.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertEqual(added, [path.stem])

    def test_every_sight_is_built_from_an_object_the_page_loads(self):
        used = {sight["type"] for data in trainer_page.maps().values() for sight in data.get("landmarks", [])}
        self.assertTrue(used)
        self.assertLessEqual(used, {path.stem for path in trainer_page.local_files() if path.parent == OBJECTS})
