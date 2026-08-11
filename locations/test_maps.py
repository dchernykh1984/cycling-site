"""Links that hand an event's start point to an outside map service.

Two things are worth pinning here. The rule about *which* point qualifies -- a forwarded link that
resolves to a city centre sends someone to the wrong place, which is worse than offering no link at
all. And the coordinate order, which differs between services: swapping it yields a URL that looks
entirely normal and points into another hemisphere.
"""

from decimal import Decimal

from django.test import TestCase

from locations.maps import map_links, start_point
from locations.models import Location, LocationFallback

# A start line in Almaty. Deliberately asymmetric: swap the two numbers and you land in the Arctic
# Ocean rather than a few streets away, so an order mistake cannot hide behind a plausible result.
# A Cyrillic venue name, written as escapes because the sources are ASCII-only: "Magazin Giant".
CYRILLIC_NAME = "\u041c\u0430\u0433\u0430\u0437\u0438\u043d Giant"

ALMATY_LAT = Decimal("43.238949")
ALMATY_LNG = Decimal("76.889709")


def _tree(**venue_kwargs):
    """country / region / city / venue, the shape every real location has."""
    country = Location.add_root(name="KZ", name_ru="KZ")
    region = country.add_child(name="Almaty region", name_ru="Almaty region")
    city = region.add_child(name="Almaty", name_ru="Almaty", lat=Decimal("43.2220"), lng=Decimal("76.8512"))
    venue = city.add_child(**{"name": "Giant store, Abaya 47", "name_ru": "Giant store, Abaya 47", **venue_kwargs})
    return country, region, city, venue


class StartPointRuleTests(TestCase):
    """Which location deserves a link at all."""

    def test_a_venue_with_its_own_point_qualifies(self):
        _, _, _, venue = _tree(lat=ALMATY_LAT, lng=ALMATY_LNG)
        self.assertEqual(start_point(venue), (ALMATY_LAT, ALMATY_LNG))

    def test_a_venue_without_a_point_offers_nothing(self):
        """No link is better than a link to nowhere."""
        _, _, _, venue = _tree()
        self.assertIsNone(start_point(venue))
        self.assertEqual(map_links(venue), [])

    def test_a_city_never_qualifies_even_though_it_has_a_point(self):
        """Someone who only needs the city types the city into their navigator."""
        _, _, city, _ = _tree()
        self.assertIsNotNone(city.lat)
        self.assertIsNone(start_point(city))
        self.assertEqual(map_links(city), [])

    def test_a_region_and_a_country_never_qualify(self):
        country, region, _, _ = _tree()
        for node in (country, region):
            node.lat, node.lng = ALMATY_LAT, ALMATY_LNG
            node.save(update_fields=["lat", "lng"])
            self.assertIsNone(start_point(node), node.name)

    def test_a_citys_catch_all_venue_offers_nothing_even_carrying_a_point(self):
        """ "Other location" means the announcement never said where -- and it may carry the city's
        own coordinates so the site can still draw a marker. Forwarding that as a start line is
        exactly the failure this rule exists to prevent."""
        _, _, city, venue = _tree(lat=ALMATY_LAT, lng=ALMATY_LNG, is_hidden=True)
        LocationFallback.objects.create(city=city, location=venue)
        venue.refresh_from_db()
        self.assertIsNone(start_point(venue))
        self.assertEqual(map_links(venue), [])

    def test_a_hidden_venue_offers_nothing(self):
        _, _, _, venue = _tree(lat=ALMATY_LAT, lng=ALMATY_LNG, is_hidden=True)
        self.assertIsNone(start_point(venue))

    def test_no_location_at_all_is_not_an_error(self):
        self.assertIsNone(start_point(None))
        self.assertEqual(map_links(None), [])

    def test_something_that_is_not_a_location_is_refused_loudly(self):
        """Failing closed matters more than being forgiving: a permissive default would hand out a
        link for an object nobody could vouch for, which is precisely what this rule prevents."""
        with self.assertRaises(AttributeError):
            start_point(object())  # type: ignore[arg-type]


class MapLinkTests(TestCase):
    """What the links actually contain."""

    def setUp(self):
        _, _, _, self.venue = _tree(lat=ALMATY_LAT, lng=ALMATY_LNG)
        self.links = {link.key: link.url for link in map_links(self.venue, CYRILLIC_NAME)}

    def test_every_service_is_offered_in_the_agreed_order(self):
        keys = [link.key for link in map_links(self.venue)]
        self.assertEqual(keys, ["2gis", "yandex", "google", "apple", "osm"])

    def test_services_that_take_longitude_first_get_longitude_first(self):
        """2GIS and Yandex read lon,lat. Swapping puts the start in the Arctic Ocean."""
        self.assertIn("76.889709,43.238949", self.links["2gis"])
        self.assertIn("pt=76.889709,43.238949", self.links["yandex"])
        self.assertIn("ll=76.889709,43.238949", self.links["yandex"])

    def test_yandex_is_told_where_to_centre_not_just_where_to_draw_a_pin(self):
        """Yandex without ll opens on the reader's own region and the pin can be off-screen."""
        url = self.links["yandex"]
        self.assertIn("ll=", url)
        self.assertLess(url.index("ll="), url.index("z="), "the zoom only applies to a given centre")

    def test_services_that_take_latitude_first_get_latitude_first(self):
        """Google, Apple and OpenStreetMap read lat,lon."""
        self.assertIn("query=43.238949,76.889709", self.links["google"])
        self.assertIn("ll=43.238949,76.889709", self.links["apple"])
        self.assertIn("mlat=43.238949", self.links["osm"])
        self.assertIn("mlon=76.889709", self.links["osm"])

    def test_no_link_carries_the_numbers_the_other_way_round(self):
        """A blunt guard: the swapped pair must appear in no URL of the other family."""
        swapped, straight = "43.238949,76.889709", "76.889709,43.238949"
        self.assertNotIn(swapped, self.links["2gis"])
        self.assertNotIn(swapped, self.links["yandex"])
        for key in ("google", "apple"):
            self.assertNotIn(straight, self.links[key])

    def test_every_url_is_https_and_absolute(self):
        for key, url in self.links.items():
            self.assertTrue(url.startswith("https://"), f"{key}: {url}")

    def test_the_venue_name_reaches_apple_url_encoded(self):
        """Apple shows a caption on the pin; an unencoded Cyrillic name would break the URL."""
        self.assertIn("q=%D0%9C", self.links["apple"])
        self.assertNotIn(" ", self.links["apple"])

    def test_a_missing_name_still_produces_working_links(self):
        links = {link.key: link.url for link in map_links(self.venue)}
        self.assertTrue(links["apple"].endswith("q="))
        self.assertEqual(len(links), 5)

    def test_coordinates_are_written_plainly_never_in_scientific_notation(self):
        """A point near the prime meridian would otherwise render as 1E-7 and land nowhere."""
        _, _, city, _ = _tree()
        venue = city.add_child(name="Near zero", name_ru="Near zero", lat=Decimal("0.0000001"), lng=Decimal("0.000001"))
        links = {link.key: link.url for link in map_links(venue)}
        # Six decimal places, plainly written -- the column stores six, so this is the full precision.
        self.assertIn("0.000001,0.000000", links["2gis"])
        self.assertIn("query=0.000000,0.000001", links["google"])
        for url in links.values():
            self.assertNotIn("E-", url)
            self.assertNotIn("e-", url.split("://", 1)[1])

    def test_a_southern_western_point_keeps_its_sign(self):
        """Negative coordinates are the ones a naive formatter mangles."""
        _, _, city, _ = _tree()
        venue = city.add_child(name="Ushuaia", name_ru="Ushuaia", lat=Decimal("-54.801912"), lng=Decimal("-68.302948"))
        links = {link.key: link.url for link in map_links(venue)}
        self.assertIn("-54.801912", links["google"])
        self.assertIn("-68.302948", links["google"])
        self.assertIn("-68.302948,-54.801912", links["2gis"])


class MapLinkLocaleTests(TestCase):
    """The heading and the labels have to exist in all three site languages."""

    def test_labels_are_present_in_every_locale(self):
        from django.utils import translation

        _, _, _, venue = _tree(lat=ALMATY_LAT, lng=ALMATY_LNG)
        for code in ("ru", "kk", "en"):
            with translation.override(code):
                labels = [link.label for link in map_links(venue)]
                self.assertEqual(len(labels), 5, code)
                for label in labels:
                    self.assertTrue(label.strip(), f"{code}: an empty service label")
