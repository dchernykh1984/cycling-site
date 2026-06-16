import datetime

from django.test import TestCase
from django.urls import reverse
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

    def test_participant_proposes_pending_location(self):
        # Issue #111: any registered user may propose a location (pending), not 403.
        self.client.force_login(self.participant)
        self.client.post(self.url, {"name_ru": "Venue", "name_kk": "", "name_en": "", "city": str(self.city.pk)})
        venue = Location.objects.filter(name_ru="Venue").first()
        self.assertIsNotNone(venue)
        self.assertTrue(venue.is_pending)
        self.assertEqual(venue.proposal.submitted_by, self.participant)

    def test_participant_cannot_create_hidden_location(self):
        # Non-managers must not be able to create hidden fallback venues.
        self.client.force_login(self.participant)
        self.client.post(
            self.url,
            {"name_ru": "Sneaky", "name_kk": "", "name_en": "", "city": str(self.city.pk), "is_hidden": "on"},
        )
        self.assertFalse(Location.objects.get(name_ru="Sneaky").is_hidden)

    def test_organizer_adds_approved_location_directly(self):
        organizer = _make_user("org_loc@x.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        self.client.post(self.url, {"name_ru": "OrgVenue", "name_kk": "", "name_en": "", "city": str(self.city.pk)})
        venue = Location.objects.get(name_ru="OrgVenue")
        self.assertFalse(venue.is_pending)
        self.assertFalse(hasattr(venue, "proposal"))

    def test_admin_get_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_creates_venue_under_city(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"name_ru": "Velodrome", "name_kk": "", "name_en": "", "city": str(self.city.pk)})
        venue = Location.objects.filter(name_ru="Velodrome").first()
        self.assertIsNotNone(venue)
        self.assertEqual(venue.depth, 4)
        self.assertEqual(venue.get_parent().pk, self.city.pk)
        self.assertFalse(venue.is_pending)

    def test_missing_city_shows_form_error(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url, {"name_ru": "Venue", "city": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("city", resp.context["form"].errors)

    def test_missing_name_ru_shows_form_error(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url, {"name_ru": "", "city": str(self.city.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("name_ru", resp.context["form"].errors)


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
        resp = self.client.post(self._url(), {"name_ru": "X", "city": str(self.city.pk)})
        self.assertEqual(resp.status_code, 403)

    def test_admin_get_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)

    def test_admin_updates_name(self):
        self.client.force_login(self.admin)
        self.client.post(self._url(), {"name_ru": "NewName", "name_kk": "", "name_en": "", "city": str(self.city.pk)})
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.name_ru, "NewName")
        self.assertEqual(self.loc.name, "NewName")

    def test_admin_changes_city(self):
        self.client.force_login(self.admin)
        new_city = self.region.add_child(name="NewCity", name_ru="NewCity", name_en="NewCity")
        self.client.post(
            self._url(),
            {"name_ru": "OldName", "name_kk": "", "name_en": "", "city": str(new_city.pk)},
        )
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.get_parent().pk, new_city.pk)

    def test_admin_hides_location(self):
        self.client.force_login(self.admin)
        self.client.post(
            self._url(),
            {"name_ru": "OldName", "name_kk": "", "name_en": "", "city": str(self.city.pk), "is_hidden": "on"},
        )
        self.loc.refresh_from_db()
        self.assertTrue(self.loc.is_hidden)

    def test_edit_depth1_location_updates_name(self):
        """Structural locations (countries) can have name updated without city field."""
        self.client.force_login(self.admin)
        url = reverse("location_edit", args=[self.country.pk])
        self.client.post(url, {"name_ru": "KZ Updated", "name_kk": "", "name_en": ""})
        self.country.refresh_from_db()
        self.assertEqual(self.country.name_ru, "KZ Updated")


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
