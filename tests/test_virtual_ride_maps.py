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
            # a fourth value is the rider's line, metres right of the road's middle: on the road, every point or none
            lined = {len(point) for point in route["pts"]}
            self.assertIn(lined, ({3}, {4}), route["id"])
            for point in route["pts"] + route.get("extend", []):
                lat, lon = point[:2]
                self.assertTrue(all(isinstance(n, Real) for n in point), route["id"])
                self.assertTrue(-90 <= lat <= 90 and -180 <= lon <= 180, route["id"])
                if len(point) == 4:
                    self.assertLessEqual(abs(point[3]), route["width"] / 2, route["id"])
            self.assertIsInstance(route.get("oneway", False), bool)
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

    def test_a_route_s_own_buildings_barriers_and_trees_have_their_shape(self):
        # a racetrack's scenery from OpenStreetMap (js/world.js): footprints with a height, a barrier's gap beyond the
        # road, rows and woods of trees -- every point a place near the route's origin
        owned = [route for route in _routes() if {"buildings", "barriers", "trees"} & set(route)]
        self.assertTrue(owned)
        origins = {
            route["id"]: route.get("origin", data.get("origin"))
            for data in trainer_page.maps().values()
            for route in data.get("routes", [])
        }
        for route in owned:
            for building in route.get("buildings", []):
                self.assertGreater(building["h"], 0, route["id"])
            if "barriers" in route:
                self.assertEqual(set(route["barriers"]), {"gap"}, route["id"])
                self.assertGreater(route["barriers"]["gap"], 0, route["id"])
                if "c" in building:
                    self.assertRegex(building["c"], r"^#[0-9a-f]{6}$", route["id"])
            trees = route.get("trees", {})
            self.assertLessEqual(set(trees), {"rows", "woods", "pts"}, route["id"])
            lines = [(row, 2) for row in trees.get("rows", [])] + [(wood, 3) for wood in trees.get("woods", [])]
            lines += [([tree], 1) for tree in trees.get("pts", [])]
            lines += [(building["pts"], 3) for building in route.get("buildings", [])]
            for line, least in lines:
                self.assertGreaterEqual(len(line), least, route["id"])
                for point in line:
                    self.assertEqual(len(point), 2, route["id"])
                    self.assertLess(_km(origins[route["id"]], point), 50, route["id"])

    def test_what_stands_round_a_route_has_its_shape(self):
        # roads round it, bridges over it and roads under it, power lines and railways, water (js/surroundings.js):
        # lines of places near the route's origin, each as wide as a road or a river is; its own bridges and tunnels
        # stretches between two of its points, a tunnel's between the ends of its ramps
        routes = [route for route in _routes() if {"roads", "over", "under", "lines", "water"} & set(route)]
        self.assertTrue(routes)
        origins = {
            route["id"]: route.get("origin", data.get("origin"))
            for data in trainer_page.maps().values()
            for route in data.get("routes", [])
        }
        for route in routes:
            near = origins[route["id"]]
            lines = [(item["pts"], item["w"]) for key in ("roads", "over", "under") for item in route.get(key, [])]
            lines += [(item["pts"], item["w"]) for item in route.get("water", []) if "pts" in item]
            lines += [(item["pts"], 1) for item in route.get("lines", [])]
            for line, wide in lines:
                self.assertGreaterEqual(len(line), 2, route["id"])
                self.assertTrue(0 < wide <= 60, route["id"])
                for point in line:
                    self.assertEqual(len(point), 2, route["id"])
                    self.assertLess(_km(near, point), 50, route["id"])
            self.assertLessEqual(
                {item["k"] for item in route.get("lines", [])}, {"power", "minor", "rail"}, route["id"]
            )
            for lake in [item["area"] for item in route.get("water", []) if "area" in item]:
                self.assertGreaterEqual(len(lake), 3, route["id"])
            last = len(route["pts"]) - 1
            for i0, i1 in route.get("bridges", []):
                self.assertTrue(0 <= i0 <= i1 <= last, route["id"])
            for r0, i0, i1, r1 in route.get("tunnels", []):
                self.assertTrue(0 <= r0 < i0 <= i1 < r1 <= last, route["id"])

    def test_a_map_s_relief_is_a_whole_grid_of_heights_round_its_routes(self):
        # SRTM heights by latitude and longitude (js/maps.js): rows from the north, every one there, each a height a
        # place on land can have, and the grid wide enough to hold every route of the map with 20 km to spare
        reliefs = {folder: data for folder, data in trainer_page.maps().items() if "relief" in data}
        self.assertTrue(reliefs)
        for folder, data in reliefs.items():
            (north, dlat, rows), (west, dlon, cols) = data["relief"]["lat"], data["relief"]["lon"]
            heights = data["relief"]["h"]
            self.assertTrue(dlat < 0 < dlon, folder)
            self.assertEqual(len(heights), rows * cols, folder)
            self.assertTrue(all(isinstance(h, int) and -430 <= h <= 8849 for h in heights), folder)
            south, east = north + dlat * (rows - 1), west + dlon * (cols - 1)
            for route in data.get("routes", []):
                for lat, lon, *_ in route["pts"]:
                    self.assertTrue(south + 0.18 < lat < north - 0.18 and west + 0.25 < lon < east - 0.25, route["id"])

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
