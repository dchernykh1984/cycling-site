from django.test import TestCase
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from accounts.models import User
from locations.models import Location, LocationsMapPage


def _get_site_root():
    site = Site.objects.filter(is_default_site=True).first()
    return site.root_page if site else Page.objects.filter(depth=1).first()


class LocationModelTests(TestCase):
    def test_create_root_location(self):
        loc = Location.add_root(name_ru="Kazakhstan", name_kk="Kazakhstan", name_en="Kazakhstan")
        self.assertEqual(loc.name_ru, "Kazakhstan")
        self.assertEqual(loc.depth, 1)

    def test_create_child_location(self):
        country = Location.add_root(name_ru="Kazakhstan", name_en="Kazakhstan")
        city = country.add_child(name_ru="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709")
        self.assertEqual(city.depth, 2)
        self.assertEqual(city.get_parent().pk, country.pk)

    def test_str_returns_name(self):
        loc = Location.add_root(name_ru="Test Location", name_en="Test Location")
        self.assertIn("Test Location", str(loc))

    def test_locations_without_coordinates_excluded_from_map(self):
        Location.add_root(name_ru="No Coords", name_en="No Coords")
        Location.add_root(name_ru="With Coords", name_en="With Coords", lat="43.0", lng="76.0")
        with_coords = Location.objects.filter(lat__isnull=False, lng__isnull=False)
        self.assertEqual(with_coords.count(), 1)
        self.assertEqual(with_coords.first().name_ru, "With Coords")


class LocationsMapPageHierarchyTests(WagtailPageTests):
    def test_can_create_map_page_under_home(self):
        from home.models import HomePage

        self.assertCanCreateAt(HomePage, LocationsMapPage)

    def test_map_page_has_no_subpages(self):
        self.assertAllowedSubpageTypes(LocationsMapPage, [])


class LocationsMapPageRenderTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        self.map_page = LocationsMapPage(title="Map", slug="map")
        root.add_child(instance=self.map_page)
        self.loc = Location.add_root(
            name_ru="Almaty",
            name_en="Almaty",
            lat="43.238949",
            lng="76.889709",
        )

    def test_map_page_renders_200(self):
        response = self.client.get(self.map_page.url)
        self.assertEqual(response.status_code, 200)

    def test_map_page_contains_locations_data(self):
        response = self.client.get(self.map_page.url)
        self.assertContains(response, "43.238949")
        self.assertContains(response, "76.889709")

    def test_map_page_locations_data_is_list(self):
        response = self.client.get(self.map_page.url)
        # json_script filter HTML-escapes " as &quot; by design; double-escaping would
        # produce &amp;quot; -- check for that instead.
        self.assertNotContains(response, "&amp;quot;")
        data = response.context["locations_data"]
        self.assertIsInstance(data, list)
        self.assertEqual(data[0]["lat"], 43.238949)

    def test_map_page_excludes_locations_without_coords(self):
        Location.add_root(name_ru="No Coords", name_en="No Coords")
        response = self.client.get(self.map_page.url)
        self.assertEqual(response.status_code, 200)
        data = response.context["locations_data"]
        names = [d["name"] for d in data]
        self.assertNotIn("No Coords", names)


class LocationArticlePageWithMapTests(TestCase):
    def setUp(self):
        from knowledge.models import KnowledgeIndexPage, LocationArticlePage

        root = _get_site_root()
        index = KnowledgeIndexPage(title="Knowledge", slug="knowledge-map-test")
        root.add_child(instance=index)
        self.article = LocationArticlePage(title="Almaty Loop", slug="almaty-loop-map")
        index.add_child(instance=self.article)

    def test_article_renders_without_linked_location(self):
        response = self.client.get(self.article.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["linked_location"])
        self.assertNotContains(response, "location-map")

    def test_article_renders_with_linked_location_with_coords(self):
        loc = Location.add_root(
            name_ru="Almaty",
            name_en="Almaty",
            lat="43.238949",
            lng="76.889709",
            knowledge_article=self.article,
        )
        response = self.client.get(self.article.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["linked_location"].pk, loc.pk)
        self.assertIn("linked_location_lat", response.context)
        self.assertContains(response, "43.238949")
        self.assertContains(response, "location-map")

    def test_article_with_linked_location_no_coords_does_not_render_invalid_js(self):
        Location.add_root(
            name_en="Country Only",
            name_ru="Country Only",
            knowledge_article=self.article,
        )
        response = self.client.get(self.article.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("linked_location_lat", response.context)
        self.assertNotContains(response, "var lat = ;")
        self.assertNotContains(response, "location-map")


class LocationSearchTests(TestCase):
    def test_location_can_be_found_via_search_backend(self):
        from wagtail.search.backends import get_search_backend

        loc = Location.add_root(name_en="Almaty City", name_ru="Almaty City", name_kk="Almaty City")
        backend = get_search_backend()
        backend.add(loc)
        results = list(backend.search("Almaty City", Location))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pk, loc.pk)

    def test_search_page_returns_200(self):
        from django.urls import reverse

        response = self.client.get(reverse("search") + "?query=Almaty")
        self.assertEqual(response.status_code, 200)


class LocationAdminFormTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="password123",
            is_staff=True,
        )

    def test_add_root_via_form_save(self):
        from locations.wagtail_hooks import LocationForm

        form = LocationForm(
            data={
                "parent": "",
                "name_ru": "Kazakhstan",
                "name_kk": "Kazakhstan",
                "name_en": "Kazakhstan",
                "lat": "",
                "lng": "",
                "knowledge_article": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        loc = form.save()
        self.assertEqual(loc.name_ru, "Kazakhstan")
        self.assertEqual(loc.depth, 1)

    def test_add_child_via_form_save(self):
        from locations.wagtail_hooks import LocationForm

        parent = Location.add_root(name_ru="Kazakhstan", name_en="Kazakhstan")
        form = LocationForm(
            data={
                "parent": str(parent.pk),
                "name_ru": "Almaty",
                "name_kk": "Almaty",
                "name_en": "Almaty",
                "lat": "43.238949",
                "lng": "76.889709",
                "knowledge_article": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        city = form.save()
        self.assertEqual(city.depth, 2)
        self.assertEqual(city.get_parent().pk, parent.pk)
