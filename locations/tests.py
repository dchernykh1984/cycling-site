import datetime
import threading

from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from accounts.models import User
from locations.models import (
    Location,
    LocationConflictError,
    LocationFallback,
    LocationProposal,
    LocationsMapPage,
    add_location_child,
    location_filter_rank,
    locations_filter_data,
    lock_competition_location,
    move_location,
    soft_delete_location,
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
        # The seeds fill the tree with coordinate-bearing countries, so assert on these two nodes
        # rather than on the whole table.
        Location.add_root(name_ru="No Coords", name_en="No Coords")
        Location.add_root(name_ru="With Coords", name_en="With Coords", lat="43.0", lng="76.0")
        with_coords = Location.objects.filter(
            lat__isnull=False, lng__isnull=False, name_ru__in=["No Coords", "With Coords"]
        )
        self.assertEqual([loc.name_ru for loc in with_coords], ["With Coords"])
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


def _make_user(username, role, is_superuser=False):
    return User.objects.create_user(
        username=username,
        email=username,
        password="pass",
        role=role,
        is_superuser=is_superuser,
    )


class LocationOrderingTests(TestCase):
    """sort_order, not creation order, decides how locations are listed."""

    def test_new_node_lands_after_the_real_ones_and_before_the_catch_all(self):
        from locations.models import CATCH_ALL_SORT_ORDER, add_location_child, selectable_parent_locations

        country = add_location_child(None, name="Country", name_ru="Country")
        add_location_child(country, name="First", name_ru="First")
        # Stands for the localized catch-all, which is pinned by its sort_order alone.
        catch_all = add_location_child(
            country, name="Other region", name_ru="Other region", sort_order=CATCH_ALL_SORT_ORDER
        )
        second = add_location_child(country, name="Second", name_ru="Second")

        self.assertLess(second.sort_order, catch_all.sort_order)
        names = [
            loc.name_ru for loc in selectable_parent_locations() if loc.depth == 2 and loc.path.startswith(country.path)
        ]
        self.assertEqual(names, ["First", "Second", "Other region"])

    def test_catch_all_venue_is_last_in_its_city(self):
        from locations.models import CATCH_ALL_SORT_ORDER, add_location_child

        _, _, city = _make_tree()
        venue = add_location_child(city, name="Real venue", name_ru="Real venue")
        fallback = Location.get_or_create_other_location(city)
        self.assertEqual(fallback.sort_order, CATCH_ALL_SORT_ORDER)
        self.assertLess(venue.sort_order, fallback.sort_order)

    def test_sort_order_decides_the_listing_and_ties_fall_back_to_creation_order(self):
        from locations.models import add_location_child, selectable_parent_locations

        def position(name):
            return [loc.name_ru for loc in selectable_parent_locations()].index(name)

        add_location_child(None, name="ZZ-A", name_ru="ZZ-A", sort_order=500)
        second = add_location_child(None, name="ZZ-B", name_ru="ZZ-B", sort_order=500)
        # Equal sort_order: the one added first leads, because nodes are appended to the tree.
        self.assertLess(position("ZZ-A"), position("ZZ-B"))

        Location.objects.filter(pk=second.pk).update(sort_order=499)
        # A lower sort_order now wins even though the node still holds the later path.
        self.assertLess(position("ZZ-B"), position("ZZ-A"))


def _propose_place(parent, name, submitted_by):
    """A pending region/city (depth 2-3), the way the API creates one for the events agent."""
    from locations.models import LocationProposal, add_location_child

    place = add_location_child(parent, name=name, name_ru=name, name_kk=name, name_en=name)
    LocationProposal.objects.create(location=place, submitted_by=submitted_by)
    return place


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

    def _post_child(self, user, parent, name):
        self.client.force_login(user)
        return self.client.post(self.url, {"name_ru": name, "parent": parent.pk if parent else ""})

    def test_organizer_proposes_a_region_through_the_form(self):
        """The web form must offer an organizer the same thing the API does.

        The events agent proposes regions and cities through the API under the organizer role; a
        human with that role would otherwise be locked out of the very workflow built for it.
        """
        organizer = _make_user("org-ui@x.com", User.Role.ORGANIZER)
        self._post_child(organizer, self.country, "Proposed Region")
        proposed = Location.objects.get(name_ru="Proposed Region")
        self.assertEqual(proposed.depth, 2)
        self.assertTrue(proposed.is_pending)
        self.assertEqual(proposed.proposal.submitted_by, organizer)

    def test_organizer_proposes_a_city_through_the_form(self):
        organizer = _make_user("org-ui-city@x.com", User.Role.ORGANIZER)
        self._post_child(organizer, self.region, "Proposed City")
        proposed = Location.objects.get(name_ru="Proposed City")
        self.assertEqual(proposed.depth, 3)
        self.assertTrue(proposed.is_pending)

    def test_organizer_venue_under_own_pending_city_stays_pending(self):
        organizer = _make_user("org-ui-chain@x.com", User.Role.ORGANIZER)
        self._post_child(organizer, self.region, "Pending City")
        pending_city = Location.objects.get(name_ru="Pending City")
        self._post_child(organizer, pending_city, "Venue In Pending")
        self.assertTrue(Location.objects.get(name_ru="Venue In Pending").is_pending)

    def test_organizer_venue_still_lands_approved(self):
        organizer = _make_user("org-ui-venue@x.com", User.Role.ORGANIZER)
        self._post_child(organizer, self.city, "Direct Venue")
        venue = Location.objects.get(name_ru="Direct Venue")
        self.assertEqual(venue.depth, 4)
        self.assertFalse(venue.is_pending)

    def test_admin_region_still_lands_approved(self):
        self._post_child(self.admin, self.country, "Admin Region")
        self.assertFalse(Location.objects.get(name_ru="Admin Region").is_pending)

    def test_participant_cannot_propose_a_region_through_the_form(self):
        # The form stops them with a field error; the view's 403 stays as defense against a forged POST.
        resp = self._post_child(self.participant, self.country, "Nope Region")
        self.assertIn("parent", resp.context["form"].errors)
        self.assertFalse(Location.objects.filter(name_ru="Nope Region").exists())

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self.url)
        self.assertRedirects(resp, f"/accounts/login/?next={self.url}", fetch_redirect_response=False)

    def test_guest_redirected_to_profile_when_opening_propose_form(self):
        # An unconfirmed user (GUEST) must verify their email (become PARTICIPANT) first.
        guest = _make_user("guest_loc@x.com", User.Role.GUEST)
        self.client.force_login(guest)
        self.assertRedirects(self.client.get(self.url), reverse("account_profile"))

    def test_guest_cannot_propose_location(self):
        guest = _make_user("guest_loc2@x.com", User.Role.GUEST)
        self.client.force_login(guest)
        resp = self.client.post(
            self.url, {"name_ru": "GuestVenue", "name_kk": "", "name_en": "", "parent": str(self.city.pk)}
        )
        self.assertRedirects(resp, reverse("account_profile"))
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

    def test_participant_incomplete_cascade_shows_field_error(self):
        # A non-manager who doesn't pick a full city gets a clear parent field error (not a 403).
        self.client.force_login(self.participant)
        resp = self.client.post(
            self.url, {"name_ru": "NewRegion", "name_kk": "", "name_en": "", "parent": str(self.country.pk)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.assertFalse(Location.objects.filter(name_ru="NewRegion").exists())

    def test_participant_empty_cascade_shows_field_error(self):
        self.client.force_login(self.participant)
        resp = self.client.post(self.url, {"name_ru": "NewCountry", "name_kk": "", "name_en": "", "parent": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.assertFalse(Location.objects.filter(name_ru="NewCountry").exists())

    def test_organizer_cannot_create_a_country(self):
        # A country is the one level an organizer may not touch: regions and cities they propose.
        organizer = _make_user("org_struct@x.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        resp = self.client.post(self.url, {"name_ru": "OrgCountry", "name_kk": "", "name_en": "", "parent": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.assertFalse(Location.objects.filter(name_ru="OrgCountry").exists())

    def test_participant_cannot_create_a_structural_node(self):
        self.client.force_login(self.participant)
        for name, parent in {
            "PartCountry": "",
            "PartRegion": str(self.country.pk),
            "PartCity": str(self.region.pk),
        }.items():
            with self.subTest(name=name):
                resp = self.client.post(self.url, {"name_ru": name, "name_kk": "", "name_en": "", "parent": parent})
                self.assertEqual(resp.status_code, 200)
                self.assertIn("parent", resp.context["form"].errors)
                self.assertFalse(Location.objects.filter(name_ru=name).exists())

    def test_incomplete_cascade_field_error_is_localized(self):
        # The "select a city" field error renders in English under en and is translated under ru.
        self.client.force_login(self.participant)
        data = {"name_ru": "X", "name_kk": "", "name_en": "", "parent": ""}
        en = self.client.post(self.url, data, HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(en, "a venue is added inside the chosen city")
        ru = self.client.post(self.url, data, HTTP_ACCEPT_LANGUAGE="ru")
        self.assertNotContains(ru, "a venue is added inside the chosen city")

    def test_organizer_can_still_create_venue(self):
        # organizer+ may add an approved depth-4 venue under a city directly (no proposal).
        organizer = _make_user("org_venue@x.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        self.client.post(self.url, {"name_ru": "OrgVenue2", "name_kk": "", "name_en": "", "parent": str(self.city.pk)})
        venue = Location.objects.get(name_ru="OrgVenue2")
        self.assertEqual(venue.depth, 4)
        self.assertFalse(venue.is_pending)

    def test_admin_creates_structural_node_approved(self):
        # Only admins may build the geographic hierarchy; the node is approved (never a proposal).
        self.client.force_login(self.admin)
        self.client.post(
            self.url, {"name_ru": "AdminRegion", "name_kk": "", "name_en": "", "parent": str(self.country.pk)}
        )
        region = Location.objects.get(name_ru="AdminRegion")
        self.assertEqual(region.depth, 2)
        self.assertFalse(region.is_pending)
        self.assertFalse(hasattr(region, "proposal"))

    def test_create_form_hint_is_role_aware_and_localized(self):
        # The venue-only hint is shown to non-managers and translated: present in English under en,
        # gone under ru (replaced by the translation), and never shown to admins (who get the
        # structural hint). Cyrillic isn't spelled out in .py, so absence under ru proves the swap.
        venue_hint_en = "added as a venue inside the chosen city"
        organizer = _make_user("org_hint@x.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        self.assertContains(self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="en"), venue_hint_en)
        self.assertNotContains(self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ru"), venue_hint_en)
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="en"), venue_hint_en)

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

    def test_fallback_cannot_be_moved_or_unhidden(self):
        fallback = Location.get_or_create_other_location(self.city)
        self.client.force_login(self.admin)
        new_city = self.region.add_child(name="NewCityForFallback", name_ru="NewCityForFallback")
        response = self.client.post(
            reverse("location_edit", args=[fallback.pk]),
            {"name_ru": fallback.name_ru, "name_kk": "", "name_en": "", "parent": str(new_city.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("parent", response.context["form"].errors)
        self.assertIn("is_hidden", response.context["form"].errors)
        fallback.refresh_from_db()
        self.assertEqual(fallback.get_parent().pk, self.city.pk)
        self.assertTrue(fallback.is_hidden)

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

    def test_edit_forbids_level_change_with_only_soft_deleted_descendants(self):
        # Even a soft-deleted descendant keeps the physical subtree non-empty: the level change
        # would still re-level it, so promoting the region to a country must be refused.
        self.city.is_deleted = True
        self.city.save(update_fields=["is_deleted"])
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[self.region.pk])
        resp = self.client.post(url, {"name_ru": "Region", "name_kk": "", "name_en": "", "parent": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["form"].errors)
        self.region.refresh_from_db()
        self.assertEqual(self.region.depth, 2)

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

    def test_edit_save_returns_to_page_and_filter(self):
        # Saving an edit returns to the page/filter the admin came from, not the first page.
        self.client.force_login(self.admin)
        resp = self.client.post(
            self._url(),
            {
                "name_ru": "OldName",
                "name_kk": "",
                "name_en": "",
                "parent": str(self.city.pk),
                "next": "/map/?page=2&location=9",
            },
        )
        self.assertRedirects(resp, "/map/?page=2&location=9", fetch_redirect_response=False)

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

    def test_cannot_delete_structural_node_with_active_subtree(self):
        # Soft-deleting a country with live region/city/venue below would orphan them.
        country, _, _ = _make_tree()
        self.client.force_login(self.admin)
        self.client.post(reverse("location_delete", args=[country.pk]))
        country.refresh_from_db()
        self.assertFalse(country.is_deleted)

    def test_delete_blocked_message_is_localized(self):
        # The "cannot delete" message renders in English under en and is translated under ru.
        msg_en = "Cannot delete a location that still has nested locations or competitions."
        self.client.force_login(self.admin)
        country, _, _ = _make_tree()
        en = self.client.post(reverse("location_delete", args=[country.pk]), HTTP_ACCEPT_LANGUAGE="en", follow=True)
        self.assertIn(msg_en, [str(m) for m in en.context["messages"]])
        ru = self.client.post(reverse("location_delete", args=[country.pk]), HTTP_ACCEPT_LANGUAGE="ru", follow=True)
        self.assertNotIn(msg_en, [str(m) for m in ru.context["messages"]])

    def test_can_delete_empty_venue(self):
        _, _, city = _make_tree()
        venue = city.add_child(name="EmptyVenue", name_ru="EmptyVenue", name_en="EmptyVenue")
        self.client.force_login(self.admin)
        self.client.post(reverse("location_delete", args=[venue.pk]))
        venue.refresh_from_db()
        self.assertTrue(venue.is_deleted)

    def test_cannot_delete_system_fallback(self):
        _, _, city = _make_tree()
        fallback = Location.get_or_create_other_location(city)
        self.client.force_login(self.admin)
        self.client.post(reverse("location_delete", args=[fallback.pk]))
        fallback.refresh_from_db()
        self.assertFalse(fallback.is_deleted)

    def test_cannot_delete_venue_with_competitions(self):
        from calendar_app.models import Competition

        _, _, city = _make_tree()
        venue = city.add_child(name="UsedVenue", name_ru="UsedVenue", name_en="UsedVenue")
        Competition.objects.create(
            title_ru="R", date_start=datetime.date(2026, 7, 1), location=venue, status=Competition.Status.APPROVED
        )
        self.client.force_login(self.admin)
        self.client.post(reverse("location_delete", args=[venue.pk]))
        venue.refresh_from_db()
        self.assertFalse(venue.is_deleted)

    def test_can_delete_venue_with_only_soft_deleted_competitions(self):
        # A soft-deleted competition no longer keeps the venue alive: it can be deleted.
        from calendar_app.models import Competition

        _, _, city = _make_tree()
        venue = city.add_child(name="ArchVenue", name_ru="ArchVenue", name_en="ArchVenue")
        Competition.objects.create(
            title_ru="R",
            date_start=datetime.date(2026, 7, 1),
            location=venue,
            status=Competition.Status.APPROVED,
            is_deleted=True,
        )
        self.client.force_login(self.admin)
        self.client.post(reverse("location_delete", args=[venue.pk]))
        venue.refresh_from_db()
        self.assertTrue(venue.is_deleted)

    def test_delete_returns_to_page_and_filter(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("location_delete", args=[self.loc.pk]), {"next": "/map/?page=3&location=7"})
        self.assertRedirects(resp, "/map/?page=3&location=7", fetch_redirect_response=False)

    def test_delete_rejects_open_redirect_next(self):
        # Off-site and scheme-relative (//, ////, \\) targets fall back to the default, never to a
        # foreign host (open-redirect guard).
        self.client.force_login(self.admin)
        for bad in (
            "https://evil.example.com/x?a=1",
            "//evil.example.com/x",
            "////evil.example.com/x",
            "https:evil.example.com",
            "\\\\evil.example.com/x",
        ):
            with self.subTest(bad=bad):
                loc = Location.add_root(name=f"D-{bad[:6]}", name_ru="D")
                resp = self.client.post(reverse("location_delete", args=[loc.pk]), {"next": bad})
                self.assertRedirects(resp, "/", fetch_redirect_response=False)

    def test_delete_allows_same_origin_relative_next(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("location_delete", args=[self.loc.pk]), {"next": "/map/?page=2"})
        self.assertRedirects(resp, "/map/?page=2", fetch_redirect_response=False)


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

    def test_hide_returns_to_page_and_filter(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("location_hide", args=[self.loc.pk]), {"next": "/map/?page=2&location=4"})
        self.assertRedirects(resp, "/map/?page=2&location=4", fetch_redirect_response=False)

    def test_system_fallback_cannot_be_unhidden(self):
        _, _, city = _make_tree()
        fallback = Location.get_or_create_other_location(city)
        self.client.force_login(self.admin)
        self.client.post(reverse("location_hide", args=[fallback.pk]))
        fallback.refresh_from_db()
        self.assertTrue(fallback.is_hidden)


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

    def test_new_location_conflict_messages_are_translated(self):
        from django.utils import translation
        from django.utils.translation import gettext

        messages = (
            "This location is not available.",
            "System fallback locations cannot be moved.",
            "System fallback locations must remain hidden.",
            "This location proposal is no longer pending.",
            "This location cannot be rejected: approved locations or a published competition are inside it.",
        )
        for lang in ("ru", "kk"):
            with translation.override(lang):
                for message in messages:
                    self.assertNotEqual(gettext(message), message, f"{message!r} is untranslated for {lang}")


class VenueUnderPendingCityTests(TestCase):
    """A venue proposed through the competition form must not outrank the city holding it."""

    def setUp(self):
        self.user = _make_user("submitter@x.com", User.Role.ORGANIZER)
        self.country, self.region, self.city = _make_tree()

    def test_competition_form_venue_stays_pending_under_a_pending_city(self):
        from calendar_app.views import _resolve_competition_location

        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = _resolve_competition_location(
            {"new_venue_name": "Start", "new_venue_city": pending_city}, self.user, approved=True
        )
        self.assertTrue(venue.is_pending)

    def test_competition_form_venue_is_approved_under_a_public_city(self):
        from calendar_app.views import _resolve_competition_location

        venue = _resolve_competition_location(
            {"new_venue_name": "Start", "new_venue_city": self.city}, self.user, approved=True
        )
        self.assertFalse(venue.is_pending)


class MoveIntoASeededParentTests(TestCase):
    """Moving a node must not fall over the sort/path mismatch the seeds deliberately create."""

    def test_move_into_a_parent_whose_children_are_not_in_path_order(self):
        from locations.models import add_location_child, move_location

        country = add_location_child(None, name="ZZ-Country", name_ru="ZZ-Country")
        # Mirrors a seeded country: the capital carries sort_order 1 at the *last* path.
        add_location_child(country, name="Plain", name_ru="Plain", sort_order=101)
        add_location_child(country, name="Catchall", name_ru="Catchall", sort_order=9999)
        add_location_child(country, name="Capital", name_ru="Capital", sort_order=1)

        other = add_location_child(None, name="ZZ-Other", name_ru="ZZ-Other")
        moved = add_location_child(other, name="Moved", name_ru="Moved")
        move_location(moved, country)  # used to raise IntegrityError -> HTTP 500

        moved.refresh_from_db()
        self.assertEqual(moved.get_parent().pk, country.pk)
        self.assertLess(moved.sort_order, 9999)  # lands after the real siblings, before the catch-all


class ModeratorReachesPendingNodesTests(TestCase):
    """A moderator must be able to pick a foreign pending node as a parent, or the queue dead-ends."""

    def test_admin_sees_a_foreign_pending_node_as_a_selectable_parent(self):
        from locations.models import selectable_parent_locations

        proposer = _make_user("foreign-proposer@x.com", User.Role.ORGANIZER)
        admin = _make_user("queue-admin@x.com", User.Role.ADMIN)
        organizer = _make_user("other-org@x.com", User.Role.ORGANIZER)
        _, region, _ = _make_tree()
        pending = _propose_place(region, "Pendign Citty", proposer)

        self.assertIn(pending.pk, [loc.pk for loc in selectable_parent_locations(admin)])
        self.assertNotIn(pending.pk, [loc.pk for loc in selectable_parent_locations(organizer)])


class MoveUnderPendingBranchTests(TestCase):
    """An approved node must not be re-parented under a branch still awaiting review."""

    def test_move_approved_under_pending_is_refused(self):
        from locations.models import LocationConflictError, add_location_child, move_location

        proposer = _make_user("move-proposer@x.com", User.Role.ORGANIZER)
        country, region, _ = _make_tree()
        approved_city = add_location_child(region, name="Approved", name_ru="Approved")
        pending_region = _propose_place(country, "Pending Region", proposer)

        with self.assertRaises(LocationConflictError):
            move_location(approved_city, pending_region)
        # The pending branch stays rejectable, which a smuggled-in approved child would have blocked.
        pending_region.reject_and_reset_competitions()

    def test_move_pending_under_pending_is_allowed(self):
        from locations.models import move_location

        proposer = _make_user("move-proposer2@x.com", User.Role.ORGANIZER)
        country, region, _ = _make_tree()
        pending_city = _propose_place(region, "Pending City", proposer)
        pending_region = _propose_place(country, "Pending Region", proposer)
        move_location(pending_city, pending_region)  # both pending -> fine
        self.assertEqual(Location.objects.get(pk=pending_city.pk).get_parent().pk, pending_region.pk)


class ReRootSortOrderTests(TestCase):
    """Re-rooting must rank the node among countries, not among every node at its old depth."""

    def test_a_re_rooted_region_sorts_with_the_countries(self):
        from locations.models import add_location_child, move_location

        country = add_location_child(None, name="ZZ-Country", name_ru="ZZ-Country")
        for i in range(6):
            add_location_child(country, name=f"R{i}", name_ru=f"R{i}")
        moved = add_location_child(country, name="ToBeCountry", name_ru="ToBeCountry")

        move_location(moved, None)
        moved.refresh_from_db()
        roots = Location.objects.filter(depth=1, is_deleted=False).exclude(pk=moved.pk)
        self.assertEqual(moved.depth, 1)
        self.assertLessEqual(moved.sort_order, max(r.sort_order for r in roots if r.sort_order < 9999) + 1)


class ManagerBuildingUnderAProposalTests(TestCase):
    """A manager may reach a pending node, but a child created there stays pending too."""

    def test_admin_child_of_a_pending_region_is_not_public(self):
        from django.urls import reverse

        proposer = _make_user("build-proposer@x.com", User.Role.ORGANIZER)
        admin = _make_user("build-admin@x.com", User.Role.ADMIN)
        _, region, _ = _make_tree()
        pending_region = _propose_place(region.get_parent(), "Pending Region", proposer)

        self.client.force_login(admin)
        self.client.post(reverse("location_add"), {"name_ru": "NewCity", "parent": pending_region.pk})
        created = Location.objects.get(name_ru="NewCity")
        self.assertTrue(created.is_pending)
        # The queue entry stays actionable, which a public child would have prevented.
        pending_region.reject_and_reset_competitions()


class CatchAllVenueLifecycleTests(TestCase):
    """A city's catch-all rides with the city; it is not a proposal to judge on its own."""

    def setUp(self):
        self.proposer = _make_user("catchall@x.com", User.Role.ORGANIZER)
        self.admin = _make_user("catchall-admin@x.com", User.Role.ADMIN)
        self.country, self.region, self.city = _make_tree()

    def _pending_city_with_fallback(self):
        from locations.models import LocationProposal

        city = _propose_place(self.region, "Pending City", self.proposer)
        venue = Location.get_or_create_other_location(city)
        LocationProposal.objects.create(location=venue, submitted_by=self.proposer)
        return city, venue

    def test_approving_the_city_approves_its_catch_all(self):
        city, venue = self._pending_city_with_fallback()
        Location.propose_venue(city, "Real", submitted_by=self.proposer).approve_with_competition(self.admin)
        venue.proposal.refresh_from_db()
        self.assertFalse(Location.objects.get(pk=venue.pk).is_pending)

    def test_the_catch_all_cannot_be_rejected_on_its_own(self):
        from locations.models import LocationInUseError

        _, venue = self._pending_city_with_fallback()
        with self.assertRaises(LocationInUseError):
            venue.reject_and_reset_competitions()
        self.assertFalse(Location.objects.get(pk=venue.pk).is_deleted)


class OrganizerSelfPublishTests(TestCase):
    """An organizer's own submission publishes itself, bypassing Competition.approve()."""

    def setUp(self):
        self.organizer = _make_user("selfpub@x.com", User.Role.ORGANIZER)
        self.country, self.region, self.city = _make_tree()

    def _submit(self, city, name):
        from django.urls import reverse

        self.client.force_login(self.organizer)
        return self.client.post(
            reverse("calendar_submit"),
            {
                "title_ru": name,
                "date_start": "2026-09-01",
                "new_venue_city": str(city.pk),
                "new_venue_name": f"{name} start",
            },
        )

    def test_submission_onto_a_pending_city_is_not_published(self):
        from calendar_app.models import Competition

        pending_city = _propose_place(self.region, "Secretville", self.organizer)
        self._submit(pending_city, "Hidden Race")
        comp = Competition.objects.get(title_ru="Hidden Race")
        self.assertEqual(comp.status, Competition.Status.PENDING_APPROVAL)
        # And the branch stays rejectable, which the published state would have prevented.
        pending_city.reject_and_reset_competitions()

    def test_submission_onto_a_public_city_is_published_as_before(self):
        from calendar_app.models import Competition

        self._submit(self.city, "Open Race")
        self.assertEqual(Competition.objects.get(title_ru="Open Race").status, Competition.Status.APPROVED)


class ApprovalBlockedByPendingGeographyTests(TestCase):
    """An organizer must not publish an event onto geography nobody has reviewed."""

    def setUp(self):
        self.proposer = _make_user("geo-proposer@x.com", User.Role.ORGANIZER)
        self.country, self.region, self.city = _make_tree()

    def test_organizer_cannot_approve_an_event_on_a_pending_branch(self):
        from calendar_app.models import Competition
        from locations.models import LocationPendingError

        organizer = _make_user("geo-approver@x.com", User.Role.ORGANIZER)
        pending_city = _propose_place(self.region, "Pending City", self.proposer)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.proposer)
        comp = Competition.objects.create(
            title_ru="C",
            date_start=datetime.date(2026, 7, 1),
            location=venue,
            status=Competition.Status.PENDING_APPROVAL,
        )
        with self.assertRaises(LocationPendingError):
            comp.approve(reviewer=organizer)
        comp.refresh_from_db()
        self.assertEqual(comp.status, Competition.Status.PENDING_APPROVAL)
        # The branch stays rejectable, which is the whole point.
        pending_city.reject_and_reset_competitions()

    def test_admin_may_approve_and_the_branch_rises_with_it(self):
        from calendar_app.models import Competition

        admin = _make_user("geo-admin@x.com", User.Role.ADMIN)
        pending_city = _propose_place(self.region, "Pending City", self.proposer)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.proposer)
        comp = Competition.objects.create(
            title_ru="C",
            date_start=datetime.date(2026, 7, 1),
            location=venue,
            status=Competition.Status.PENDING_APPROVAL,
        )
        comp.approve(reviewer=admin)
        self.assertFalse(Location.objects.get(pk=pending_city.pk).is_pending)


class LocationLevelLabelTests(TestCase):
    """A moderator reviewing a proposal has to see what level it is and what sits above it."""

    def test_level_label_and_ancestors(self):
        from django.utils import translation

        country, region, city = _make_tree()
        venue = add_location_child(city, name="Start", name_ru="Start")
        with translation.override("en"):
            labels = [node.get_level_label() for node in (country, region, city, venue)]
        self.assertEqual(labels, ["Country", "Region", "City", "Venue"])
        self.assertEqual(country.ancestor_label, "")
        self.assertEqual(venue.ancestor_label, "KZ, Region, City")

    def test_level_label_is_translated(self):
        from django.utils import translation

        country, _, _ = _make_tree()
        for lang in ("ru", "kk"):
            with translation.override(lang):
                self.assertNotEqual(country.get_level_label(), "Country", f"untranslated for {lang}")


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

    def test_get_or_create_other_location_reuses_explicit_fallback(self):
        existing = self.city.add_child(name="Other", name_ru="Other", is_hidden=True)
        LocationFallback.objects.create(city=self.city, location=existing)
        self.assertEqual(Location.get_or_create_other_location(self.city).pk, existing.pk)

    def test_get_or_create_other_location_does_not_reuse_an_ordinary_hidden_venue(self):
        hidden = self.city.add_child(name="Private venue", name_ru="Private venue", is_hidden=True)
        fallback = Location.get_or_create_other_location(self.city)
        self.assertNotEqual(fallback.pk, hidden.pk)
        self.assertTrue(fallback.is_system_fallback)
        self.assertEqual(fallback.fallback_identity.city_id, self.city.pk)

    def test_admin_approval_also_approves_pending_ancestors(self):
        from locations.models import LocationProposal

        admin = _make_user("adm-loc@x.com", User.Role.ADMIN)
        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user)
        venue.approve_with_competition(admin)
        pending_city.proposal.refresh_from_db()
        self.assertEqual(pending_city.proposal.status, LocationProposal.Status.APPROVED)

    def test_organizer_approval_leaves_the_geography_pending(self):
        # Competitions are moderated by ORGANIZER+, locations only by ADMIN+. Approving an event
        # must not become a back door for blessing the region and city proposed alongside it.
        from locations.models import LocationProposal

        organizer = _make_user("org-loc@x.com", User.Role.ORGANIZER)
        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user)
        venue.approve_with_competition(organizer)
        venue.proposal.refresh_from_db()
        pending_city.proposal.refresh_from_db()
        # Neither is blessed: the venue sits under geography the organizer may not approve, and
        # publishing it there would make the city unrejectable.
        self.assertEqual(venue.proposal.status, LocationProposal.Status.PENDING_APPROVAL)
        self.assertEqual(pending_city.proposal.status, LocationProposal.Status.PENDING_APPROVAL)

    def test_organizer_approval_leaves_the_venue_pending_under_pending_geography(self):
        """Approving the event must not publish a venue whose city is still a proposal.

        It would leak the city's name through the competition and leave the branch holding approved
        work, which then makes the city impossible to reject.
        """
        organizer = _make_user("org-chain@x.com", User.Role.ORGANIZER)
        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user)
        venue.approve_with_competition(organizer)
        self.assertTrue(Location.objects.get(pk=venue.pk).is_pending)
        pending_city.reject_and_reset_competitions()  # still rejectable
        self.assertTrue(Location.objects.get(pk=pending_city.pk).is_deleted)

    def test_rejecting_a_proposed_city_ignores_a_rejected_competition(self):
        from calendar_app.models import Competition

        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user)
        comp = Competition.objects.create(
            title_ru="C", date_start=datetime.date(2026, 7, 1), location=venue, status=Competition.Status.REJECTED
        )
        pending_city.reject_and_reset_competitions()
        comp.refresh_from_db()
        self.assertIsNone(comp.location)

    def test_rejecting_a_proposed_city_refuses_when_a_published_competition_is_inside(self):
        from calendar_app.models import Competition
        from locations.models import LocationInUseError

        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user)
        comp = Competition.objects.create(
            title_ru="C", date_start=datetime.date(2026, 7, 1), location=venue, status=Competition.Status.APPROVED
        )
        with self.assertRaises(LocationInUseError):
            pending_city.reject_and_reset_competitions()
        pending_city.refresh_from_db()
        comp.refresh_from_db()
        self.assertFalse(pending_city.is_deleted)  # the branch survives rather than taking the event with it
        self.assertEqual(comp.location_id, venue.pk)

    def test_rejecting_a_proposed_city_refuses_when_it_holds_an_approved_location(self):
        from locations.models import LocationInUseError

        pending_city = _propose_place(self.region, "Pending City", self.user)
        approved_venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user, approved=True)
        with self.assertRaises(LocationInUseError):
            pending_city.reject_and_reset_competitions()
        approved_venue.refresh_from_db()
        self.assertFalse(approved_venue.is_deleted)

    def test_rejecting_a_proposed_city_clears_its_fallback_mappings(self):
        pending_city = _propose_place(self.region, "Pending City", self.user)
        fallback = Location.get_or_create_other_location(pending_city)
        pending_city.reject_and_reset_competitions()
        fallback.refresh_from_db()
        self.assertTrue(fallback.is_deleted)
        self.assertFalse(LocationFallback.objects.filter(city=pending_city).exists())

    def test_rejecting_a_proposed_city_drops_the_branch_and_unbinds_competitions(self):
        from calendar_app.models import Competition

        pending_city = _propose_place(self.region, "Pending City", self.user)
        venue = Location.propose_venue(pending_city, "Venue", submitted_by=self.user)
        comp = Competition.objects.create(title_ru="C", date_start=datetime.date(2026, 7, 1), location=venue)
        pending_city.reject_and_reset_competitions()
        pending_city.refresh_from_db()
        venue.refresh_from_db()
        comp.refresh_from_db()
        self.assertTrue(pending_city.is_deleted)
        self.assertTrue(venue.is_deleted)  # the whole branch goes, not just the node
        self.assertIsNone(comp.location)  # no stand-in exists, so a human re-places the event

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
        self.assertTrue(comp.location.is_system_fallback)
        self.assertEqual(comp.location.fallback_identity.city_id, self.city.pk)
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

    def test_manager_list_reads_as_a_hierarchy_not_by_sort_order(self):
        """The table pages through the whole tree, so it must stay in tree order.

        sort_order ranks siblings; applying it across depths interleaves branches and would list a
        country's capital above the country itself.
        """
        country = add_location_child(None, name="ZZ-Country", name_ru="ZZ-Country", sort_order=900)
        region = add_location_child(country, name="ZZ-Region", name_ru="ZZ-Region", sort_order=1)
        add_location_child(region, name="ZZ-City", name_ru="ZZ-City", sort_order=1)
        self.client.force_login(self.admin)

        names = [
            loc.name_ru for loc in self.client.get(self.map_page.url).context["locations_page"].paginator.object_list
        ]
        self.assertLess(names.index("ZZ-Country"), names.index("ZZ-Region"))
        self.assertLess(names.index("ZZ-Region"), names.index("ZZ-City"))

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

    def test_fallback_row_has_no_hide_or_delete_actions(self):
        _, _, city = _make_tree()
        fallback = Location.get_or_create_other_location(city)
        self.client.force_login(self.admin)
        html = self.client.get(self.map_page.url).content.decode()
        self.assertNotIn(reverse("location_hide", args=[fallback.pk]), html)
        self.assertNotIn(reverse("location_delete", args=[fallback.pk]), html)


class AddLocationChildConcurrencyGuardTests(TestCase):
    """add_location_child refuses to nest under a removed or already-deepest parent (the guards
    that make the locked re-check meaningful)."""

    def test_add_under_deleted_parent_raises_conflict(self):
        country = Location.add_root(name="C", name_ru="C")
        country.is_deleted = True
        country.save(update_fields=["is_deleted"])
        with self.assertRaises(LocationConflictError):
            add_location_child(country, name="R", name_ru="R")

    def test_add_under_depth4_parent_raises_conflict(self):
        country = Location.add_root(name="C", name_ru="C")
        venue = (
            country.add_child(name="R", name_ru="R")
            .add_child(name="City", name_ru="City")
            .add_child(name="V", name_ru="V")
        )
        self.assertEqual(venue.depth, 4)
        with self.assertRaises(LocationConflictError):
            add_location_child(venue, name="X", name_ru="X")


class ConcurrentLocationMutationTests(TransactionTestCase):
    """The locked check-then-act in the mutation helpers must serialize with a racing create, so a
    concurrent create can never leave a live node under a deleted or re-levelled ancestor. Driven
    at the model-helper level (the locking primitive the views use) to avoid template rendering."""

    def setUp(self):
        self.country = Location.add_root(name="KZ", name_ru="KZ")
        self.region = self.country.add_child(name="R", name_ru="R")
        self.city = self.region.add_child(name="City", name_ru="City")

    def _run(self, fn_a, fn_b):
        """Run two mutations against the same node simultaneously; return {key: outcome} where
        outcome is 'ok', 'conflict' (the expected serialized loser) or a repr of a real crash."""
        barrier = threading.Barrier(2)
        outcomes: dict = {}

        def wrap(key, fn):
            try:
                barrier.wait(timeout=10)
                fn()
                outcomes[key] = "ok"
            except LocationConflictError:
                outcomes[key] = "conflict"
            except Exception as exc:  # surface a real crash (IntegrityError etc.) as a failure
                outcomes[key] = repr(exc)
            finally:
                connections.close_all()  # release the thread's connection so teardown can drop the DB

        threads = {
            "a": threading.Thread(target=wrap, args=("a", fn_a)),
            "b": threading.Thread(target=wrap, args=("b", fn_b)),
        }
        for t in threads.values():
            t.start()
        for t in threads.values():
            t.join(timeout=15)
        # Fail loudly on a hung/deadlocked thread instead of silently passing the invariant on the
        # one result that did get recorded.
        alive = [key for key, t in threads.items() if t.is_alive()]
        self.assertEqual(alive, [], f"threads did not finish (deadlock/timeout?): {alive}")
        self.assertEqual(set(outcomes), {"a", "b"}, outcomes)
        for key, outcome in outcomes.items():
            self.assertIn(outcome, ("ok", "conflict"), f"{key} crashed: {outcome}")
        return outcomes

    def test_create_under_node_being_deleted_never_orphans(self):
        self._run(
            lambda: soft_delete_location(self.city),
            lambda: add_location_child(self.city, name="V", name_ru="V"),
        )
        self.city.refresh_from_db()
        live_children = Location.objects.filter(
            path__startswith=self.city.path, depth__gt=self.city.depth, is_deleted=False
        )
        # Never both: a deleted city with a live venue still hanging off it would be an orphan.
        self.assertFalse(self.city.is_deleted and live_children.exists())

    def test_create_under_node_being_relevelled_keeps_tree_valid(self):
        # Promote the (empty) city to a country while a venue is being added under it.
        self._run(
            lambda: move_location(self.city, None),
            lambda: add_location_child(self.city, name="V", name_ru="V"),
        )
        # Whichever order won, no live node ends up deeper than the four-level tree.
        self.assertEqual(Location.objects.filter(is_deleted=False, depth__gt=4).count(), 0)

    def test_move_vs_target_delete_never_orphans(self):
        # Move the region (with its city) under a second country while that country is being deleted.
        target = Location.add_root(name="C2", name_ru="C2")
        self._run(
            lambda: move_location(self.region, target),
            lambda: soft_delete_location(target),
        )
        target.refresh_from_db()
        self.region.refresh_from_db()
        parent = self.region.get_parent()
        # Never both: the target deleted while the region now hangs under it.
        self.assertFalse(target.is_deleted and parent is not None and parent.pk == target.pk)

    def test_move_vs_target_move_keeps_depth_within_limit(self):
        # A makes the (empty) region a child of the city (depth 4); B makes the city a child of
        # another city (depth 4). Either ordering must be refused so nothing lands at depth 5.
        source = self.country.add_child(name="S", name_ru="S")
        other_city = self.region.add_child(name="OtherCity", name_ru="OtherCity")
        self._run(
            lambda: move_location(source, self.city),
            lambda: move_location(self.city, other_city),
        )
        self.assertEqual(Location.objects.filter(is_deleted=False, depth__gt=4).count(), 0)

    def test_same_depth_subtree_move_serializes_with_add_under_descendant(self):
        target_country = Location.add_root(name="C2", name_ru="C2")
        self._run(
            lambda: move_location(self.region, target_country),
            lambda: add_location_child(self.city, name="ConcurrentVenue", name_ru="ConcurrentVenue"),
        )
        self.city.refresh_from_db()
        venue = Location.objects.get(name="ConcurrentVenue")
        self.assertEqual(venue.get_parent().pk, self.city.pk)
        self.assertTrue(venue.path.startswith(self.city.path))

    def test_independent_moves_restore_modeltranslation_global_method(self):
        from modeltranslation.manager import MultilingualQuerySet

        source_a = self.country.add_child(name="A", name_ru="A")
        source_b = Location.add_root(name="BRoot", name_ru="BRoot").add_child(name="B", name_ru="B")
        target_a = Location.add_root(name="ATarget", name_ru="ATarget")
        target_b = Location.add_root(name="BTarget", name_ru="BTarget")
        original = MultilingualQuerySet._rewrite_f
        self._run(lambda: move_location(source_a, target_a), lambda: move_location(source_b, target_b))
        self.assertIs(MultilingualQuerySet._rewrite_f, original)

    def test_reject_serializes_with_competition_binding(self):
        from calendar_app.models import Competition

        proposer = _make_user("reject-race@example.com", User.Role.PARTICIPANT)
        venue = Location.propose_venue(self.city, "PendingRaceVenue", submitted_by=proposer)

        def bind_competition():
            with transaction.atomic():
                locked = lock_competition_location(venue, proposer)
                Competition.objects.create(
                    title_ru="Race",
                    date_start=datetime.date(2026, 7, 1),
                    location=locked,
                    submitted_by=proposer,
                )

        self._run(venue.reject_and_reset_competitions, bind_competition)
        for competition in Competition.objects.select_related("location"):
            self.assertFalse(competition.location.is_deleted)

    def test_rejecting_a_proposed_city_serializes_with_competition_approval(self):
        """The published-competition guard must hold under a concurrent approval.

        Approving a competition only takes a row lock when it writes, so the reject has to lock the
        competitions before reading their status -- otherwise it can blank the location of one that
        became published in between, which is exactly what it promises to refuse.
        """
        from calendar_app.models import Competition

        proposer = _make_user("reject-approve@example.com", User.Role.PARTICIPANT)
        reviewer = _make_user("reject-approver@example.com", User.Role.ADMIN)
        pending_city = _propose_place(self.region, "RaceyCity", proposer)
        venue = Location.propose_venue(pending_city, "RaceyVenue", submitted_by=proposer)
        competition = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 7, 1),
            location=venue,
            submitted_by=proposer,
            status=Competition.Status.PENDING_APPROVAL,
        )

        self._run(pending_city.reject_and_reset_competitions, lambda: competition.approve(reviewer=reviewer))
        competition.refresh_from_db()
        # Either the reject won (location cleared while still pending) or the approval won (the
        # competition is published and keeps its venue) -- never published with no location.
        if competition.status == Competition.Status.APPROVED:
            self.assertIsNotNone(competition.location_id)

    def test_rejecting_a_proposed_city_serializes_with_competition_binding(self):
        """The depth<4 branch must lock its subtree before touching competitions.

        A competition write locks its venue row and then writes the competition. If the rejection
        cleared competitions first and only afterwards marked the branch deleted, a submission
        landing in between would survive pointing at a location that no longer exists -- and the two
        paths taking their locks in opposite orders is also what deadlocks them.
        """
        from calendar_app.models import Competition

        proposer = _make_user("reject-city-race@example.com", User.Role.PARTICIPANT)
        pending_city = _propose_place(self.region, "PendingRaceCity", proposer)
        venue = Location.propose_venue(pending_city, "PendingRaceVenue", submitted_by=proposer)

        def bind_competition():
            with transaction.atomic():
                locked = lock_competition_location(venue, proposer)
                Competition.objects.create(
                    title_ru="Race",
                    date_start=datetime.date(2026, 7, 1),
                    location=locked,
                    submitted_by=proposer,
                )

        self._run(pending_city.reject_and_reset_competitions, bind_competition)
        for competition in Competition.objects.select_related("location"):
            self.assertTrue(competition.location is None or not competition.location.is_deleted)

    def test_concurrent_rejects_share_one_city_fallback(self):
        proposer = _make_user("double-reject@example.com", User.Role.PARTICIPANT)
        first = Location.propose_venue(self.city, "PendingOne", submitted_by=proposer)
        second = Location.propose_venue(self.city, "PendingTwo", submitted_by=proposer)
        outcomes = self._run(first.reject_and_reset_competitions, second.reject_and_reset_competitions)
        self.assertEqual(set(outcomes.values()), {"ok"})
        self.assertEqual(LocationFallback.objects.filter(city=self.city).count(), 1)

    def test_concurrent_root_creates_do_not_collide(self):
        # Two parallel root creates must not pick the same treebeard path (no IntegrityError/500).
        outcomes = self._run(
            lambda: add_location_child(None, name="RootA", name_ru="RootA"),
            lambda: add_location_child(None, name="RootB", name_ru="RootB"),
        )
        self.assertEqual(set(outcomes.values()), {"ok"})  # both succeeded
        roots = Location.objects.filter(depth=1, name__in=["RootA", "RootB"])
        self.assertEqual(roots.count(), 2)
        self.assertEqual(len({r.path for r in roots}), 2)  # distinct paths
