import datetime

from django.test import TestCase
from django.urls import reverse
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from accounts.models import User
from locations.models import (
    Location,
    LocationProposal,
    LocationsMapPage,
    add_location_child,
    location_filter_rank,
    locations_filter_data,
    sort_locations_for_filter,
)


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
        self.map_page = LocationsMapPage(title="Map Render Test", slug="map-render-test")
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

    def test_add_location_cta_hidden_for_anonymous(self):
        response = self.client.get(self.map_page.url)
        self.assertFalse(response.context["can_add"])
        self.assertNotContains(response, reverse("location_add"))

    def test_add_location_cta_hidden_for_guest(self):
        # Issue #118: a guest cannot propose a location, so the CTA must not be shown
        # (clicking it would only hit the backend 403).
        guest = _make_user("map_guest@x.com", User.Role.GUEST)
        self.client.force_login(guest)
        response = self.client.get(self.map_page.url)
        self.assertFalse(response.context["can_add"])
        self.assertNotContains(response, reverse("location_add"))

    def test_add_location_cta_shown_for_participant(self):
        participant = _make_user("map_part@x.com", User.Role.PARTICIPANT)
        self.client.force_login(participant)
        response = self.client.get(self.map_page.url)
        self.assertTrue(response.context["can_add"])
        self.assertContains(response, reverse("location_add"))


class LocationsMapHiddenResolutionTests(TestCase):
    """Hidden 'other location' nodes are shown on the map at the nearest ancestor with
    coordinates, labelled with that ancestor's name; skipped if none has coords (issue #113)."""

    def setUp(self):
        root = _get_site_root()
        self.map_page = LocationsMapPage(title="Map Hidden Test", slug="map-hidden-test")
        root.add_child(instance=self.map_page)

    def _data(self):
        return self.client.get(self.map_page.url).context["locations_data"]

    def test_hidden_resolves_to_city_and_dedupes(self):
        country = Location.add_root(name="KZ", name_ru="KZ")
        region = country.add_child(name="Region", name_ru="Region")
        city = region.add_child(name="Almaty", name_ru="Almaty", lat="43.200000", lng="76.900000")
        city.add_child(name="Other location", name_ru="Other location", is_hidden=True)
        almaty = [d for d in self._data() if d["name"] == "Almaty"]
        self.assertEqual(len(almaty), 1)  # one marker, not city + resolved-hidden
        self.assertAlmostEqual(almaty[0]["lat"], 43.2)
        self.assertNotIn("Other location", [d["name"] for d in self._data()])

    def test_hidden_falls_back_to_region_when_city_has_no_coords(self):
        country = Location.add_root(name="KZ2", name_ru="KZ2")
        region = country.add_child(name="RegionC", name_ru="RegionC", lat="48.000000", lng="66.000000")
        city = region.add_child(name="NoCoordCity", name_ru="NoCoordCity")
        city.add_child(name="Other location", name_ru="Other location", is_hidden=True)
        data = self._data()
        self.assertNotIn("NoCoordCity", [d["name"] for d in data])
        region_pts = [d for d in data if d["name"] == "RegionC"]
        self.assertEqual(len(region_pts), 1)
        self.assertAlmostEqual(region_pts[0]["lat"], 48.0)

    def test_hidden_skipped_when_no_ancestor_has_coords(self):
        country = Location.add_root(name="KZ3", name_ru="KZ3")
        region = country.add_child(name="R3", name_ru="R3")
        city = region.add_child(name="C3", name_ru="C3")
        city.add_child(name="Other location", name_ru="Other location", is_hidden=True)
        names = [d["name"] for d in self._data()]
        for n in ("Other location", "C3", "R3", "KZ3"):
            self.assertNotIn(n, names)

    def test_hidden_ancestor_with_coords_is_never_a_marker(self):
        # A hidden node is skipped as a resolution target even if it has coordinates.
        country = Location.add_root(name="KZ4", name_ru="KZ4", lat="48.000000", lng="68.000000")
        hidden_region = country.add_child(name="HiddenR", name_ru="HiddenR", is_hidden=True, lat="50.0", lng="50.0")
        city = hidden_region.add_child(name="C4", name_ru="C4")
        city.add_child(name="Other location", name_ru="Other location", is_hidden=True)
        names = [d["name"] for d in self._data()]
        self.assertNotIn("HiddenR", names)
        self.assertIn("KZ4", names)  # resolution skipped the hidden region up to the country


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
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        city = form.save()
        self.assertEqual(city.depth, 2)
        self.assertEqual(city.get_parent().pk, parent.pk)


def _make_user(username, role, is_superuser=False):
    return User.objects.create_user(
        username=username,
        email=username,
        password="pass",
        role=role,
        is_superuser=is_superuser,
    )


def _make_tree():
    """Minimal 4-level tree: KZ -> Region -> City -> (returned as dict)."""
    country = Location.add_root(name="KZ", name_ru="KZ", name_en="KZ")
    region = country.add_child(name="Region", name_ru="Region", name_en="Region")
    city = region.add_child(name="City", name_ru="City", name_en="City")
    return country, region, city


class LocationCreateViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("admin@x.com", User.Role.ADMIN)
        self.participant = _make_user("part@x.com", User.Role.PARTICIPANT)
        self.url = reverse("location_add")
        self.country, self.region, self.city = _make_tree()

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self.url)
        self.assertRedirects(resp, f"/accounts/login/?next={self.url}", fetch_redirect_response=False)

    def test_guest_cannot_open_propose_form(self):
        # An unconfirmed user (GUEST) must verify their email (become PARTICIPANT) first.
        guest = _make_user("guest_loc@x.com", User.Role.GUEST)
        self.client.force_login(guest)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_guest_cannot_propose_location(self):
        guest = _make_user("guest_loc2@x.com", User.Role.GUEST)
        self.client.force_login(guest)
        resp = self.client.post(
            self.url, {"name_ru": "GuestVenue", "name_kk": "", "name_en": "", "parent": str(self.city.pk)}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Location.objects.filter(name_ru="GuestVenue").exists())

    def test_participant_proposes_pending_location(self):
        # Issue #111: any registered user may propose a location (pending), not 403.
        self.client.force_login(self.participant)
        self.client.post(self.url, {"name_ru": "Venue", "name_kk": "", "name_en": "", "parent": str(self.city.pk)})
        venue = Location.objects.filter(name_ru="Venue").first()
        self.assertIsNotNone(venue)
        self.assertTrue(venue.is_pending)
        self.assertEqual(venue.proposal.submitted_by, self.participant)

    def test_participant_cannot_create_hidden_location(self):
        # Non-managers must not be able to create hidden fallback venues.
        self.client.force_login(self.participant)
        self.client.post(
            self.url,
            {"name_ru": "Sneaky", "name_kk": "", "name_en": "", "parent": str(self.city.pk), "is_hidden": "on"},
        )
        self.assertFalse(Location.objects.get(name_ru="Sneaky").is_hidden)

    def test_organizer_adds_approved_location_directly(self):
        organizer = _make_user("org_loc@x.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        self.client.post(self.url, {"name_ru": "OrgVenue", "name_kk": "", "name_en": "", "parent": str(self.city.pk)})
        venue = Location.objects.get(name_ru="OrgVenue")
        self.assertFalse(venue.is_pending)
        self.assertFalse(hasattr(venue, "proposal"))

    def test_participant_cannot_create_structural_node(self):
        # Proposals are venue-only; a participant may not create a region/city (structural node).
        self.client.force_login(self.participant)
        resp = self.client.post(
            self.url, {"name_ru": "NewRegion", "name_kk": "", "name_en": "", "parent": str(self.country.pk)}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Location.objects.filter(name_ru="NewRegion").exists())

    def test_participant_cannot_create_country(self):
        self.client.force_login(self.participant)
        resp = self.client.post(self.url, {"name_ru": "NewCountry", "name_kk": "", "name_en": "", "parent": ""})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Location.objects.filter(name_ru="NewCountry").exists())

    def test_organizer_creates_structural_node_approved(self):
        # organizer+ may create structural nodes directly, always approved (never a proposal).
        organizer = _make_user("org_struct@x.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        self.client.post(
            self.url, {"name_ru": "OrgRegion", "name_kk": "", "name_en": "", "parent": str(self.country.pk)}
        )
        region = Location.objects.get(name_ru="OrgRegion")
        self.assertEqual(region.depth, 2)
        self.assertFalse(region.is_pending)
        self.assertFalse(hasattr(region, "proposal"))

    def test_foreign_pending_parent_is_not_selectable(self):
        # Another user's pending node must not appear as a parent in the cascade or validate on POST.
        other = _make_user("other_owner@x.com", User.Role.PARTICIPANT)
        pending_city = self.region.add_child(name="PendingCity", name_ru="PendingCity", name_en="PendingCity")
        LocationProposal.objects.create(location=pending_city, submitted_by=other)
        self.client.force_login(self.participant)
        json_pks = {row["pk"] for row in self.client.get(self.url).context["all_locations_json"]}
        self.assertNotIn(pending_city.pk, json_pks)
        resp = self.client.post(
            self.url, {"name_ru": "Venue", "name_kk": "", "name_en": "", "parent": str(pending_city.pk)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.assertFalse(Location.objects.filter(name_ru="Venue").exists())

    def test_admin_get_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_creates_venue_under_city(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"name_ru": "Velodrome", "name_kk": "", "name_en": "", "parent": str(self.city.pk)})
        venue = Location.objects.filter(name_ru="Velodrome").first()
        self.assertIsNotNone(venue)
        self.assertEqual(venue.depth, 4)
        self.assertEqual(venue.get_parent().pk, self.city.pk)
        self.assertFalse(venue.is_pending)

    def test_empty_parent_creates_country(self):
        # No parent selected -> the new location is a depth-1 country (root).
        self.client.force_login(self.admin)
        self.client.post(self.url, {"name_ru": "Mongolia", "name_kk": "", "name_en": "", "parent": ""})
        country = Location.objects.filter(name_ru="Mongolia").first()
        self.assertIsNotNone(country)
        self.assertEqual(country.depth, 1)
        self.assertIsNone(country.get_parent())

    def test_country_parent_creates_region(self):
        # Selecting only a country -> the new location is a depth-2 region under it.
        self.client.force_login(self.admin)
        self.client.post(
            self.url, {"name_ru": "NewRegion", "name_kk": "", "name_en": "", "parent": str(self.country.pk)}
        )
        region = Location.objects.filter(name_ru="NewRegion").first()
        self.assertIsNotNone(region)
        self.assertEqual(region.depth, 2)
        self.assertEqual(region.get_parent().pk, self.country.pk)

    def test_region_parent_creates_city(self):
        # Selecting country + region -> the new location is a depth-3 city under the region.
        self.client.force_login(self.admin)
        self.client.post(self.url, {"name_ru": "NewCity", "name_kk": "", "name_en": "", "parent": str(self.region.pk)})
        city = Location.objects.filter(name_ru="NewCity").first()
        self.assertIsNotNone(city)
        self.assertEqual(city.depth, 3)
        self.assertEqual(city.get_parent().pk, self.region.pk)

    def test_missing_name_ru_shows_form_error(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url, {"name_ru": "", "parent": str(self.city.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("name_ru", resp.context["form"].errors)

    def test_venues_json_lists_only_selectable_venues_with_coords(self):
        # Issue #118: the form map shows existing selectable venues (depth-4, not hidden, with coords).
        self.city.add_child(name_ru="Stadium", name_en="Stadium", lat="43.200000", lng="76.900000")
        self.city.add_child(name_ru="NoCoords", name_en="NoCoords")  # no coords -> excluded
        self.city.add_child(name_ru="Hidden", name_en="Hidden", is_hidden=True, lat="43.3", lng="77.0")  # excluded
        pending = self.city.add_child(name_ru="Pending", name_en="Pending", lat="43.4", lng="77.1")
        LocationProposal.objects.create(location=pending, submitted_by=self.participant)  # unapproved -> excluded
        self.client.force_login(self.admin)
        venues = self.client.get(self.url).context["venues_json"]
        names = {v["name_ru"] for v in venues}
        self.assertEqual(names, {"Stadium"})
        stadium = next(v for v in venues if v["name_ru"] == "Stadium")
        self.assertAlmostEqual(stadium["lat"], 43.2, places=5)
        self.assertAlmostEqual(stadium["lng"], 76.9, places=5)


class LocationEditViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("admin2@x.com", User.Role.ADMIN)
        self.participant = _make_user("part2@x.com", User.Role.PARTICIPANT)
        self.country, self.region, self.city = _make_tree()
        self.loc = self.city.add_child(name="OldName", name_ru="OldName", name_en="OldName")

    def _url(self):
        return reverse("location_edit", args=[self.loc.pk])

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self._url())
        self.assertRedirects(resp, f"/accounts/login/?next={self._url()}", fetch_redirect_response=False)

    def test_participant_forbidden(self):
        self.client.force_login(self.participant)
        resp = self.client.post(self._url(), {"name_ru": "X", "parent": str(self.city.pk)})
        self.assertEqual(resp.status_code, 403)

    def test_admin_get_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)

    def test_edit_preserves_distinct_translations_under_each_locale(self):
        # Regression: writing the canonical ``name`` via the modeltranslation descriptor under a
        # non-default active locale used to overwrite that locale's translation with the RU value
        # (e.g. under kk, name_kk became the RU name). name_ru/kk/en are concrete columns, so
        # reading them back reflects the true stored translation (no active-language rewrite).
        self.client.force_login(self.admin)
        for lang in ("ru", "kk", "en"):
            with self.subTest(lang=lang):
                loc = self.city.add_child(name="OldName", name_ru="OldName", name_kk="OldName", name_en="OldName")
                self.client.post(
                    reverse("location_edit", args=[loc.pk]),
                    {"name_ru": "RuName", "name_kk": "KkName", "name_en": "EnName", "parent": str(self.city.pk)},
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                loc.refresh_from_db()
                self.assertEqual(loc.name_ru, "RuName")
                self.assertEqual(loc.name_kk, "KkName")
                self.assertEqual(loc.name_en, "EnName")

    def test_admin_updates_name(self):
        self.client.force_login(self.admin)
        self.client.post(self._url(), {"name_ru": "NewName", "name_kk": "", "name_en": "", "parent": str(self.city.pk)})
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.name_ru, "NewName")
        self.assertEqual(self.loc.name, "NewName")

    def test_admin_changes_city(self):
        self.client.force_login(self.admin)
        new_city = self.region.add_child(name="NewCity", name_ru="NewCity", name_en="NewCity")
        self.client.post(
            self._url(),
            {"name_ru": "OldName", "name_kk": "", "name_en": "", "parent": str(new_city.pk)},
        )
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.get_parent().pk, new_city.pk)

    def test_admin_hides_location(self):
        self.client.force_login(self.admin)
        self.client.post(
            self._url(),
            {"name_ru": "OldName", "name_kk": "", "name_en": "", "parent": str(self.city.pk), "is_hidden": "on"},
        )
        self.loc.refresh_from_db()
        self.assertTrue(self.loc.is_hidden)

    def test_edit_depth1_location_updates_name(self):
        """Structural locations (countries) can have their name updated with no parent selected."""
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[self.country.pk])
        self.client.post(url, {"name_ru": "KZ Updated", "name_kk": "", "name_en": "", "parent": ""})
        self.country.refresh_from_db()
        self.assertEqual(self.country.name_ru, "KZ Updated")

    def test_edit_demotes_venue_to_city_when_city_cleared(self):
        # A depth-4 venue whose parent is changed to the region (city level "--") becomes a depth-3 city.
        self.client.force_login(self.admin)
        self.client.post(
            self._url(),
            {"name_ru": "OldName", "name_kk": "", "name_en": "", "parent": str(self.region.pk)},
        )
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.depth, 3)
        self.assertEqual(self.loc.get_parent().pk, self.region.pk)

    def test_edit_allows_level_change_for_childless_node(self):
        # A region with no children/competitions can be promoted to a depth-1 country.
        childless = self.country.add_child(name="Empty", name_ru="Empty", name_en="Empty")
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[childless.pk])
        self.client.post(url, {"name_ru": "Empty", "name_kk": "", "name_en": "", "parent": ""})
        childless.refresh_from_db()
        self.assertEqual(childless.depth, 1)
        self.assertIsNone(childless.get_parent())

    def test_edit_forbids_level_change_when_node_has_children(self):
        # self.region has a child city, so promoting it to a country (a level change) is rejected.
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[self.region.pk])
        resp = self.client.post(url, {"name_ru": "Region", "name_kk": "", "name_en": "", "parent": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.region.refresh_from_db()
        self.assertEqual(self.region.depth, 2)  # unchanged
        self.assertEqual(self.region.get_parent().pk, self.country.pk)

    def test_edit_forbids_level_change_when_venue_has_competitions(self):
        # A depth-4 venue with a competition cannot be demoted: competitions require a venue.
        from calendar_app.models import Competition

        Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 7, 1),
            location=self.loc,
            status=Competition.Status.APPROVED,
        )
        self.client.force_login(self.admin)
        resp = self.client.post(
            self._url(),
            {"name_ru": "OldName", "name_kk": "", "name_en": "", "parent": str(self.region.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.depth, 4)  # unchanged

    def test_edit_rejects_descendant_as_parent(self):
        # Making a country a child of its own region would create a cycle -> validation error.
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[self.country.pk])
        resp = self.client.post(url, {"name_ru": "KZ", "name_kk": "", "name_en": "", "parent": str(self.region.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.country.refresh_from_db()
        self.assertEqual(self.country.depth, 1)

    def test_cycle_error_is_localized(self):
        # The cycle validation message must be translated: present in English under en, absent
        # under ru (replaced by the Russian translation, which we avoid spelling out in .py).
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[self.country.pk])
        data = {"name_ru": "KZ", "name_kk": "", "name_en": "", "parent": str(self.region.pk)}
        en = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(en, "cannot be placed inside itself")
        ru = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE="ru")
        self.assertNotContains(ru, "cannot be placed inside itself")

    def test_edit_get_prefills_parent_with_current_parent(self):
        # The hidden parent field is pre-filled with the location's current parent (its city).
        self.client.force_login(self.admin)
        resp = self.client.get(self._url())
        self.assertEqual(resp.context["form"].initial["parent"].pk, self.city.pk)

    def test_edit_get_prefills_coords_with_dot_under_ru_locale(self):
        # Regression: under the ru locale Django L10N formats Decimals with a comma ("43,26"),
        # which an <input type=number> rejects, leaving lat/lng blank. They must be pre-filled
        # with a dot decimal separator so the inputs (and the map marker) populate.
        venue = self.city.add_child(name="Coords", name_ru="Coords", name_en="Coords", lat="43.263815", lng="76.817484")
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("location_edit", args=[venue.pk]), HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('value="43.263815"', html)
        self.assertIn('value="76.817484"', html)
        self.assertNotIn("43,263815", html)  # the comma form must not appear
        self.assertNotIn("76,817484", html)


class LocationDeleteViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("admin3@x.com", User.Role.ADMIN)
        self.loc = Location.add_root(name="ToDelete", name_ru="ToDelete", name_en="ToDelete")

    def test_soft_delete_sets_is_deleted(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("location_delete", args=[self.loc.pk]))
        self.loc.refresh_from_db()
        self.assertTrue(self.loc.is_deleted)

    def test_participant_forbidden(self):
        part = _make_user("part3@x.com", User.Role.PARTICIPANT)
        self.client.force_login(part)
        resp = self.client.post(reverse("location_delete", args=[self.loc.pk]))
        self.assertEqual(resp.status_code, 403)


class LocationHideViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("admin4@x.com", User.Role.ADMIN)
        self.loc = Location.add_root(name="Visible", name_ru="Visible", name_en="Visible")

    def test_toggle_hides_location(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("location_hide", args=[self.loc.pk]))
        self.loc.refresh_from_db()
        self.assertTrue(self.loc.is_hidden)

    def test_toggle_twice_restores_visibility(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("location_hide", args=[self.loc.pk]))
        self.client.post(reverse("location_hide", args=[self.loc.pk]))
        self.loc.refresh_from_db()
        self.assertFalse(self.loc.is_hidden)


class LocationsMapLocaleTests(TestCase):
    """The map page must render (not 404) and be localized in all three locales."""

    def test_map_page_renders_localized_in_all_locales(self):
        from django.utils import translation
        from django.utils.translation import gettext as _

        for lang in ("ru", "kk", "en"):
            response = self.client.get("/map/", HTTP_ACCEPT_LANGUAGE=lang)
            self.assertEqual(response.status_code, 200, f"map page should be 200 for locale {lang}")
            self.assertContains(response, "locations-map")  # the map page itself rendered, not a 404
            with translation.override(lang):
                self.assertContains(response, _("Map"))  # heading localized to the active locale


class LocationProposalModelTests(TestCase):
    """Location approval workflow helpers (issue #111)."""

    def setUp(self):
        self.user = _make_user("proposer@x.com", User.Role.PARTICIPANT)
        self.country, self.region, self.city = _make_tree()

    def test_propose_venue_is_pending_with_submitter(self):
        venue = Location.propose_venue(self.city, "My Venue", submitted_by=self.user)
        self.assertTrue(venue.is_pending)
        self.assertEqual(venue.proposal.submitted_by, self.user)
        self.assertEqual(venue.get_parent().pk, self.city.pk)
        self.assertFalse(venue.is_hidden)

    def test_propose_venue_approved_flag(self):
        venue = Location.propose_venue(self.city, "Approved Venue", submitted_by=self.user, approved=True)
        self.assertFalse(venue.is_pending)
        self.assertFalse(hasattr(venue, "proposal"))

    def test_approve_with_competition_sets_approved(self):
        from locations.models import LocationProposal

        venue = Location.propose_venue(self.city, "Pending Venue", submitted_by=self.user)
        venue.approve_with_competition()
        venue.proposal.refresh_from_db()
        self.assertEqual(venue.proposal.status, LocationProposal.Status.APPROVED)
        self.assertFalse(venue.is_pending)

    def test_get_or_create_other_location_creates_hidden_child(self):
        other = Location.get_or_create_other_location(self.city)
        self.assertTrue(other.is_hidden)
        self.assertEqual(other.get_parent().pk, self.city.pk)
        # Idempotent: returns the same node next time.
        self.assertEqual(Location.get_or_create_other_location(self.city).pk, other.pk)

    def test_get_or_create_other_location_reuses_existing_hidden(self):
        existing = self.city.add_child(name="Other", name_ru="Other", is_hidden=True)
        self.assertEqual(Location.get_or_create_other_location(self.city).pk, existing.pk)

    def test_reject_resets_competitions_to_other_location(self):
        from calendar_app.models import Competition

        venue = Location.propose_venue(self.city, "Rejected Venue", submitted_by=self.user)
        comp = Competition.objects.create(title_ru="C", date_start=datetime.date(2026, 7, 1), location=venue)
        venue.reject_and_reset_competitions()
        venue.refresh_from_db()
        comp.refresh_from_db()
        self.assertTrue(venue.is_deleted)
        self.assertIsNotNone(comp.location)
        self.assertTrue(comp.location.is_hidden)
        self.assertEqual(comp.location.get_parent().pk, self.city.pk)


class LocationApproveRejectViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("locmod@x.com", User.Role.ADMIN)
        self.participant = _make_user("locpart@x.com", User.Role.PARTICIPANT)
        self.country, self.region, self.city = _make_tree()
        self.venue = Location.propose_venue(self.city, "Pending Venue", submitted_by=self.participant)

    def test_participant_cannot_approve(self):
        self.client.force_login(self.participant)
        resp = self.client.post(reverse("location_approve", args=[self.venue.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_admin_approves(self):
        from locations.models import LocationProposal

        self.client.force_login(self.admin)
        self.client.post(reverse("location_approve", args=[self.venue.pk]))
        self.venue.proposal.refresh_from_db()
        self.assertEqual(self.venue.proposal.status, LocationProposal.Status.APPROVED)

    def test_participant_cannot_reject(self):
        self.client.force_login(self.participant)
        resp = self.client.post(reverse("location_reject", args=[self.venue.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_admin_rejects_and_resets_competition(self):
        from calendar_app.models import Competition

        comp = Competition.objects.create(title_ru="C", date_start=datetime.date(2026, 7, 1), location=self.venue)
        self.client.force_login(self.admin)
        self.client.post(reverse("location_reject", args=[self.venue.pk]))
        self.venue.refresh_from_db()
        comp.refresh_from_db()
        self.assertTrue(self.venue.is_deleted)
        self.assertTrue(comp.location.is_hidden)

    def test_reject_non_pending_location_returns_404_and_keeps_competition(self):
        from calendar_app.models import Competition

        approved = self.city.add_child(name="Approved", name_ru="Approved")  # no proposal -> not pending
        comp = Competition.objects.create(title_ru="C2", date_start=datetime.date(2026, 7, 1), location=approved)
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("location_reject", args=[approved.pk]))
        self.assertEqual(resp.status_code, 404)
        approved.refresh_from_db()
        comp.refresh_from_db()
        self.assertFalse(approved.is_deleted)
        self.assertEqual(comp.location_id, approved.pk)

    def test_approve_non_pending_location_returns_404(self):
        approved = self.city.add_child(name="Approved2", name_ru="Approved2")
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("location_approve", args=[approved.pk]))
        self.assertEqual(resp.status_code, 404)


class AddLocationChildRobustnessTests(TestCase):
    """add_location_child / propose_venue must not collide when a city's child path order
    drifts from its sort order (e.g. after a rename) or its numchild drifts. Treebeard's
    sorted add_child shifts sibling paths and used to raise IntegrityError -> 500 (#118)."""

    def _city(self):
        country = Location.add_root(name="KZ", name_ru="KZ")
        region = country.add_child(name="R", name_ru="R")
        return region.add_child(name="City", name_ru="City")

    def _child_paths(self, city):
        return list(
            Location.objects.filter(
                depth=city.depth + 1, path__range=Location._get_children_path_interval(city.path)
            ).values_list("path", flat=True)
        )

    def test_append_after_rename_desync_does_not_collide(self):
        city = self._city()
        for nm in ["A", "B", "D", "E"]:
            city.add_child(name=nm, name_ru=nm, sort_order=0)
        first = city.get_children().order_by("path").first()
        first.name = first.name_ru = "Z"  # path stays first, sort order moves last -> desync
        first.save()
        city.refresh_from_db()
        venue = add_location_child(city, name="M", name_ru="M")
        self.assertEqual(venue.get_parent().pk, city.pk)
        paths = self._child_paths(city)
        self.assertEqual(len(paths), 5)
        self.assertEqual(len(paths), len(set(paths)))  # no duplicate path

    def test_append_heals_numchild_zero(self):
        city = self._city()
        city.add_child(name="A", name_ru="A")
        Location.objects.filter(pk=city.pk).update(numchild=0)  # looks like a leaf
        city.refresh_from_db()
        add_location_child(city, name="B", name_ru="B")
        city.refresh_from_db()
        self.assertEqual(city.numchild, 2)
        paths = self._child_paths(city)
        self.assertEqual(len(paths), len(set(paths)))

    def test_append_heals_numchild_too_high(self):
        city = self._city()
        city.add_child(name="A", name_ru="A")
        Location.objects.filter(pk=city.pk).update(numchild=9)
        city.refresh_from_db()
        add_location_child(city, name="B", name_ru="B")
        city.refresh_from_db()
        self.assertEqual(city.numchild, 2)

    def test_get_or_create_other_no_duplicate_under_numchild_zero(self):
        city = self._city()
        first = Location.get_or_create_other_location(city)
        Location.objects.filter(pk=city.pk).update(numchild=0)
        city.refresh_from_db()
        second = Location.get_or_create_other_location(city)
        self.assertEqual(first.pk, second.pk)

    def test_propose_venue_after_rename_creates_pending(self):
        city = self._city()
        city.add_child(name="A", name_ru="A", sort_order=0)
        existing = city.get_children().order_by("path").first()
        existing.name = existing.name_ru = "Z"
        existing.save()
        city.refresh_from_db()
        venue = Location.propose_venue(city, "New venue")
        self.assertTrue(venue.is_pending)
        self.assertEqual(venue.get_parent().pk, city.pk)

    def test_repeated_appends_with_renames_keep_unique_paths(self):
        city = self._city()
        for i in range(8):
            add_location_child(city, name=f"v{i}", name_ru=f"v{i}", sort_order=0)
            first = city.get_children().order_by("path").first()
            first.name = first.name_ru = f"z{i}"  # keep desyncing each round
            first.save()
            city.refresh_from_db()
        paths = self._child_paths(city)
        self.assertEqual(len(paths), 8)
        self.assertEqual(len(paths), len(set(paths)))


class LocationFilterOrderingTests(TestCase):
    """Cascade filter dropdowns must list visible+coords nodes first, then visible without
    coords, then hidden+coords, then hidden without coords (hidden / coordinate-less last)."""

    def test_rank_orders_the_four_groups(self):
        self.assertEqual(location_filter_rank({"is_hidden": False, "lat": 1.0, "lng": 1.0}), 0)
        self.assertEqual(location_filter_rank({"is_hidden": False, "lat": None, "lng": None}), 1)
        self.assertEqual(location_filter_rank({"is_hidden": True, "lat": 1.0, "lng": 1.0}), 2)
        self.assertEqual(location_filter_rank({"is_hidden": True, "lat": None, "lng": None}), 3)

    def test_sort_is_stable_within_a_group(self):
        rows = [
            {"name": "v_coords_1", "is_hidden": False, "lat": 1.0, "lng": 1.0},
            {"name": "hidden_coords", "is_hidden": True, "lat": 1.0, "lng": 1.0},
            {"name": "v_no_coords", "is_hidden": False, "lat": None, "lng": None},
            {"name": "hidden_no_coords", "is_hidden": True, "lat": None, "lng": None},
            {"name": "v_coords_2", "is_hidden": False, "lat": 2.0, "lng": 2.0},
        ]
        ordered = [r["name"] for r in sort_locations_for_filter(rows)]
        # Two visible+coords keep their original relative order, then visible-no-coords,
        # then hidden+coords, then hidden-no-coords.
        self.assertEqual(ordered, ["v_coords_1", "v_coords_2", "v_no_coords", "hidden_coords", "hidden_no_coords"])

    def test_locations_filter_data_orders_hidden_and_coordless_last(self):
        Location.add_root(name="A", name_ru="A", name_en="A", lat="43.000000", lng="76.000000")
        Location.add_root(name="HiddenCoords", name_ru="HiddenCoords", is_hidden=True, lat="44.0", lng="77.0")
        Location.add_root(name="NoCoords", name_ru="NoCoords", name_en="NoCoords")
        Location.add_root(name="HiddenNoCoords", name_ru="HiddenNoCoords", is_hidden=True)
        Location.add_root(name="B", name_ru="B", name_en="B", lat="45.000000", lng="78.000000")
        created = {"A", "B", "NoCoords", "HiddenCoords", "HiddenNoCoords"}
        names = [r["name_ru"] for r in locations_filter_data() if r["name_ru"] in created]
        self.assertEqual(names, ["A", "B", "NoCoords", "HiddenCoords", "HiddenNoCoords"])


class LocationsMapPageManageListTests(TestCase):
    """The map page shows managers a paginated, filterable location list and a per-marker
    edit link; non-managers see neither."""

    def setUp(self):
        root = _get_site_root()
        self.map_page = LocationsMapPage(title="Map Manage Test", slug="map-manage-test")
        root.add_child(instance=self.map_page)
        self.admin = _make_user("map_admin@x.com", User.Role.ADMIN)
        self.participant = _make_user("map_part2@x.com", User.Role.PARTICIPANT)

    def test_manager_list_is_paginated(self):
        for i in range(25):
            Location.add_root(name=f"C{i:02d}", name_ru=f"C{i:02d}", name_en=f"C{i:02d}")
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url)
        page = resp.context["locations_page"]
        self.assertEqual(len(page), 20)  # first page is full
        self.assertGreaterEqual(page.paginator.count, 25)
        self.assertGreater(page.paginator.num_pages, 1)

    def test_second_page_returns_remaining(self):
        for i in range(25):
            Location.add_root(name=f"D{i:02d}", name_ru=f"D{i:02d}", name_en=f"D{i:02d}")
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url, {"page": 2})
        self.assertEqual(resp.context["locations_page"].number, 2)

    def test_pagination_renders_editable_page_input(self):
        for i in range(25):
            Location.add_root(name=f"F{i:02d}", name_ru=f"F{i:02d}", name_en=f"F{i:02d}")
        self.client.force_login(self.admin)
        html = self.client.get(self.map_page.url).content.decode()
        self.assertIn('name="page"', html)
        self.assertIn('type="number"', html)
        self.assertIn("page-jump", html)  # CSS hook that hides the spinner arrows

    def test_list_hidden_for_anonymous(self):
        Location.add_root(name="Solo", name_ru="Solo", name_en="Solo")
        resp = self.client.get(self.map_page.url)
        self.assertNotIn("locations_page", resp.context)
        self.assertNotContains(resp, "Manage locations")

    def test_list_hidden_for_participant(self):
        self.client.force_login(self.participant)
        resp = self.client.get(self.map_page.url)
        self.assertNotIn("locations_page", resp.context)

    def test_filter_narrows_list_to_selected_subtree(self):
        country_a, region_a, city_a = _make_tree()
        country_b = Location.add_root(name="OtherCountry", name_ru="OtherCountry", name_en="OtherCountry")
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url, {"location": str(country_a.pk)})
        pks = {loc.pk for loc in resp.context["locations_page"]}
        self.assertEqual(pks, {country_a.pk, region_a.pk, city_a.pk})
        self.assertNotIn(country_b.pk, pks)

    def test_filter_narrows_map_markers(self):
        country_a = Location.add_root(name="AA", name_ru="AA", name_en="AA", lat="43.200000", lng="76.900000")
        Location.add_root(name="BB", name_ru="BB", name_en="BB", lat="51.100000", lng="71.400000")
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url, {"location": str(country_a.pk)})
        names = {d["name"] for d in resp.context["locations_data"]}
        self.assertIn("AA", names)
        self.assertNotIn("BB", names)

    def test_filter_by_coordless_node_resolves_to_ancestor_coords(self):
        # Filtering by a coordinate-less city must still show a marker at its ancestor's
        # coordinates (the same fallback as the unfiltered map), not an empty map.
        country = Location.add_root(name="KZf", name_ru="KZf", name_en="KZf", lat="48.000000", lng="68.000000")
        region = country.add_child(name="Rf", name_ru="Rf", name_en="Rf")  # no coords
        city = region.add_child(name="Cf", name_ru="Cf", name_en="Cf")  # no coords
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url, {"location": str(city.pk)})
        data = resp.context["locations_data"]
        self.assertEqual(len(data), 1)
        self.assertAlmostEqual(data[0]["lat"], 48.0)
        self.assertEqual(data[0]["name"], "KZf")

    def test_filter_data_present_for_manager(self):
        _make_tree()
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url)
        data = resp.context["filter_locations_data"]
        self.assertTrue(any(row["name_ru"] == "KZ" for row in data))
        self.assertContains(resp, "filter-locations-data")

    def test_manager_filter_data_includes_foreign_pending(self):
        # The management table shows every non-deleted node, including other users' pending ones,
        # so the search cascade must include them too (admin must be able to find them by name).
        other = _make_user("pend_owner@x.com", User.Role.PARTICIPANT)
        _, _, city = _make_tree()
        venue = city.add_child(name="ForeignPending", name_ru="ForeignPending", name_en="ForeignPending")
        LocationProposal.objects.create(location=venue, submitted_by=other)
        self.client.force_login(self.admin)
        resp = self.client.get(self.map_page.url)
        pks = {row["pk"] for row in resp.context["filter_locations_data"]}
        self.assertIn(venue.pk, pks)

    def test_popup_edit_link_shown_only_to_manager(self):
        # The JS popup builds an edit link from the {location_edit 0} template URL, emitted
        # only when the viewer can manage locations.
        edit_url_tpl = reverse("location_edit", args=[0])
        self.client.force_login(self.admin)
        self.assertIn(edit_url_tpl, self.client.get(self.map_page.url).content.decode())
        self.client.logout()
        self.assertNotIn(edit_url_tpl, self.client.get(self.map_page.url).content.decode())
