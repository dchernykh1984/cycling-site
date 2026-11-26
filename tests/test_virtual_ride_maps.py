"""The virtual ride's maps -- a city each, in a folder of the trainer's maps/, nothing but data -- and the objects
their sights are built from, a file each in objects/, shared by every map. The page lists them all."""

import math
import re
from numbers import Real

from django.test import SimpleTestCase

from api.endpoints.virtual_ride import _ROUTE
from tests import trainer_page
from trainer.models import VirtualRide

# The members' saved rides and group races keep the key of the route they were ridden on
RIDDEN = {"center", "medeu", "oldtown", "farabi", "kyrbaltabay-tuganbay"}  # the last live since 2026-11-26
# What world.js draws along a route
SCENERIES = {"city", "gorge", "steppe", "racetrack"}
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

    def test_the_maps_load_after_their_registry_and_before_the_route_is_picked(self):
        files, code = trainer_page.local_files(), trainer_page.PAGE.parent / "alatau" / "js"
        listed = [files.index(path) for path in files if path.parent.parent == trainer_page.MAPS]
        # addMap is js/maps.js's; js/race.js picks the route out of ROUTES as it loads
        self.assertLess(files.index(code / "maps.js"), min(listed))
        self.assertLess(max(listed), files.index(code / "race.js"))

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

    def test_a_route_and_a_sight_are_laid_out_from_a_point_near_them(self):
        # the scene is flat: 50 km north or south of its origin a map's east-west metres are about 1 % off; a route
        # far from its map's others -- a region's lie tens of kilometres apart -- carries its own origin
        for folder, data in trainer_page.maps().items():
            routes = data.get("routes", [])
            for route in routes:
                origin = route.get("origin", data.get("origin"))
                self.assertIsNotNone(origin, f"{route['id']} has no origin, nor has its map")
                points = route["pts"] + route.get("extend", [])
                self.assertLess(max(_km(origin, point) for point in points), 50, route["id"])
            # a sight is drawn from the origin of the route it stands by; a map without routes draws none
            origins = [route.get("origin", data.get("origin")) for route in routes]
            for sight in data.get("landmarks", []) if origins else []:
                self.assertLess(min(_km(origin, (sight["lat"], sight["lon"])) for origin in origins), 50, folder)

    def test_a_map_s_and_a_route_s_mountains_say_how_far_south_they_rise(self):
        ranges = {folder: data["mountains"] for folder, data in trainer_page.maps().items() if "mountains" in data}
        ranges |= {route["id"]: route["mountains"] for route in _routes() if "mountains" in route}
        self.assertTrue(ranges)
        for where, mountains in ranges.items():
            self.assertEqual(set(mountains), {"south"}, where)
            self.assertGreater(mountains["south"], 0, where)

    def test_a_sight_stands_at_a_place(self):
        for folder, data in trainer_page.maps().items():
            for sight in data.get("landmarks", []):
                self.assertIsInstance(sight["type"], str, folder)
                self.assertTrue(-90 <= sight["lat"] <= 90 and -180 <= sight["lon"] <= 180, sight["type"])
                self.assertGreater(sight["r"], 0, sight["type"])

    def test_a_route_s_key_is_its_own_across_every_map_and_one_the_site_takes(self):
        keys = [route["id"] for route in _routes()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLessEqual(RIDDEN, set(keys), "a route already ridden lost its key, and its records with it")
        # the API saves a ride, a group race and a position only under a key like these
        self.assertEqual([key for key in keys if not re.fullmatch(_ROUTE, key)], [])

    def test_every_route_carries_the_event_announcing_a_group_race_on_it(self):
        # "Add event" fills the event form with it: what an event's form takes, in every language, the race's own
        # link and time in its description; the type and the discipline by the English names the lists have
        placeholders = {"link", "time", "date", "km", "climb", "wind", "join"}
        for route in _routes():
            event = route["event"]
            for part in ("title", "preview", "text"):
                self.assertEqual(set(event[part]), {"ru", "kk", "en"}, route["id"])
                for text in event[part].values():
                    self.assertTrue(text.strip(), route["id"])
                    self.assertLessEqual(set(re.findall(r"\{(\w+)\}", text)), placeholders, (route["id"], text))
            for text in event["text"].values():
                self.assertIn('<a href="{link}">', text, route["id"])
                self.assertIn("{time}", text, route["id"])
            self.assertTrue(all(text.strip() for text in event["types"] + event["disciplines"]), route["id"])

    def test_a_route_s_name_fits_the_site_in_every_language(self):
        # the page sends the name it shows with a saved ride and a group race, as it is
        longest = VirtualRide._meta.get_field("route_name").max_length
        names = [text for route in _routes() for text in route["name"].values()]
        self.assertTrue(names)
        self.assertEqual([name for name in names if len(name) > longest], [])


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
