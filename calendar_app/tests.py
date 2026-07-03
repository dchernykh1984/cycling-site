import datetime
import json

from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from accounts.models import User
from calendar_app.models import Competition, CompetitionComment, Discipline, DisciplineCategory, EventType
from locations.models import Location


def _make_user(email, role, is_staff=False):
    return User.objects.create_user(
        username=email,
        email=email,
        password="password123",
        role=role,
        is_staff=is_staff,
    )


def _make_competition(title="Test Race", status=Competition.Status.APPROVED, **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": datetime.date(2026, 7, 1),
        "status": status,
    }
    defaults.update(kwargs)
    # disciplines is a many-to-many - set it after the row exists.
    disciplines = defaults.pop("disciplines", None)
    comp = Competition.objects.create(**defaults)
    if disciplines:
        comp.disciplines.set(disciplines)
    return comp


class CompetitionModelTests(TestCase):
    def setUp(self):
        self.organizer = _make_user("organizer@example.com", User.Role.ORGANIZER)
        self.comp = _make_competition(status=Competition.Status.PENDING_APPROVAL)

    def test_approve_sets_status(self):
        self.comp.approve(reviewer=self.organizer)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, Competition.Status.APPROVED)
        self.assertEqual(self.comp.approved_by, self.organizer)
        self.assertIsNotNone(self.comp.approved_at)

    def test_reject_sets_status_and_reason(self):
        self.comp.reject(reviewer=self.organizer, reason="Not relevant")
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, Competition.Status.REJECTED)
        self.assertEqual(self.comp.rejection_reason, "Not relevant")

    def test_double_approve_raises_error(self):
        self.comp.approve(reviewer=self.organizer)
        with self.assertRaises(ValueError):
            self.comp.approve(reviewer=self.organizer)

    def test_approve_rejected_raises_error(self):
        self.comp.reject(reviewer=self.organizer)
        with self.assertRaises(ValueError):
            self.comp.approve(reviewer=self.organizer)

    def test_get_calendar_end_with_date_end(self):
        self.comp.date_end = datetime.date(2026, 7, 3)
        self.comp.save()
        self.assertEqual(self.comp.get_calendar_end(), "2026-07-04")

    def test_get_calendar_end_without_date_end(self):
        self.assertIsNone(self.comp.get_calendar_end())

    def test_str(self):
        self.assertEqual(str(self.comp), "Test Race")


class CalendarViewTests(TestCase):
    def test_calendar_returns_200(self):
        response = self.client.get(reverse("calendar"))
        self.assertEqual(response.status_code, 200)

    def test_calendar_has_context(self):
        response = self.client.get(reverse("calendar"))
        self.assertIn("event_types", response.context)
        self.assertIn("discipline_categories", response.context)
        self.assertIn("disciplines_json", response.context)
        self.assertIn("locations_data", response.context)


class CalendarEventsAPIViewTests(TestCase):
    def setUp(self):
        self.event_type = EventType.objects.create(name_ru="Race")
        self.category = DisciplineCategory.objects.create(name_ru="Road Cycling")
        self.discipline = Discipline.objects.create(name_ru="Road", category=self.category)
        self.comp1 = _make_competition(
            "Race A",
            status=Competition.Status.APPROVED,
            date_start=datetime.date(2026, 7, 10),
            event_type=self.event_type,
            disciplines=[self.discipline],
        )
        self.comp2 = _make_competition(
            "Race B",
            status=Competition.Status.APPROVED,
            date_start=datetime.date(2026, 8, 5),
        )
        self.pending = _make_competition(
            "Pending Race",
            status=Competition.Status.PENDING_APPROVAL,
            date_start=datetime.date(2026, 7, 15),
        )

    def test_returns_only_approved(self):
        response = self.client.get(reverse("calendar_events_api"))
        data = json.loads(response.content)
        titles = [e["title"] for e in data]
        self.assertIn("Race A", titles)
        self.assertIn("Race B", titles)
        self.assertNotIn("Pending Race", titles)

    def test_date_range_filter(self):
        response = self.client.get(
            reverse("calendar_events_api"),
            {"start": "2026-07-01", "end": "2026-08-01"},
        )
        data = json.loads(response.content)
        titles = [e["title"] for e in data]
        self.assertIn("Race A", titles)
        self.assertNotIn("Race B", titles)

    def test_event_type_filter(self):
        response = self.client.get(
            reverse("calendar_events_api"),
            {"event_type": self.event_type.pk},
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Race A")

    def test_discipline_filter(self):
        response = self.client.get(
            reverse("calendar_events_api"),
            {"discipline": self.discipline.pk},
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Race A")

    def test_event_has_url(self):
        response = self.client.get(reverse("calendar_events_api"))
        data = json.loads(response.content)
        self.assertTrue(all("url" in e for e in data))

    def test_multiday_event_starting_before_range_is_included(self):
        _make_competition(
            "Multi-day",
            status=Competition.Status.APPROVED,
            date_start=datetime.date(2026, 6, 30),
            date_end=datetime.date(2026, 7, 2),
        )
        response = self.client.get(
            reverse("calendar_events_api"),
            {"start": "2026-07-01", "end": "2026-08-01"},
        )
        data = json.loads(response.content)
        titles = [e["title"] for e in data]
        self.assertIn("Multi-day", titles)


class CompetitionListViewTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.comp = _make_competition(
            "Upcoming Race",
            status=Competition.Status.APPROVED,
            date_start=today + datetime.timedelta(days=5),
        )
        self.old = _make_competition(
            "Past Race",
            status=Competition.Status.APPROVED,
            date_start=today - datetime.timedelta(days=60),
        )

    def test_list_returns_200(self):
        response = self.client.get(reverse("calendar_list"))
        self.assertEqual(response.status_code, 200)

    def test_shows_upcoming_by_default(self):
        response = self.client.get(reverse("calendar_list"))
        titles = [c.title for c in response.context["competitions"]]
        self.assertIn("Upcoming Race", titles)

    def test_past_not_shown_by_default(self):
        response = self.client.get(reverse("calendar_list"))
        titles = [c.title for c in response.context["competitions"]]
        self.assertNotIn("Past Race", titles)

    def test_pagination_renders_editable_page_input(self):
        today = timezone.localdate()
        for i in range(25):
            _make_competition(f"Race {i:02d}", date_start=today + datetime.timedelta(days=i + 1))
        html = self.client.get(reverse("calendar_list")).content.decode()
        self.assertIn('name="page"', html)
        self.assertIn('type="number"', html)
        self.assertIn("page-jump", html)  # CSS hook that hides the spinner arrows

    def test_can_jump_to_arbitrary_page(self):
        today = timezone.localdate()
        for i in range(25):
            _make_competition(f"Race {i:02d}", date_start=today + datetime.timedelta(days=i + 1))
        response = self.client.get(reverse("calendar_list"), {"page": 2})
        self.assertEqual(response.context["competitions"].number, 2)

    def test_date_range_filter(self):
        past_date = (timezone.localdate() - datetime.timedelta(days=60)).isoformat()
        response = self.client.get(
            reverse("calendar_list"),
            {"date_from": past_date, "date_to": past_date},
        )
        titles = [c.title for c in response.context["competitions"]]
        self.assertIn("Past Race", titles)
        self.assertNotIn("Upcoming Race", titles)


class CompetitionDetailViewTests(TestCase):
    def setUp(self):
        self.owner = _make_user("owner@example.com", User.Role.PARTICIPANT)
        self.comp = _make_competition(status=Competition.Status.APPROVED, submitted_by=self.owner)
        self.pending = _make_competition("Pending", status=Competition.Status.PENDING_APPROVAL)
        self.url = reverse("competition_detail", args=[self.comp.pk])

    def _token(self):
        return str(self.comp.upload_token)

    def test_detail_returns_200_for_approved(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_detail_prefetches_disciplines(self):
        # direction_label + disciplines_label both walk disciplines (and their categories); the
        # view must prefetch them so the query count does not grow with the number of disciplines.
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        cats = [DisciplineCategory.objects.create(name_ru=f"C{i}", order=i) for i in range(3)]
        discs = [Discipline.objects.create(name_ru=f"D{i}", category=cats[i], order=i) for i in range(3)]
        one = _make_competition("One disc", disciplines=[discs[0]])
        many = _make_competition("Many disc", disciplines=discs)
        self.client.get(reverse("competition_detail", args=[one.pk]))  # warm process-level caches
        with CaptureQueriesContext(connection) as q_one:
            self.client.get(reverse("competition_detail", args=[one.pk]))
        with CaptureQueriesContext(connection) as q_many:
            self.client.get(reverse("competition_detail", args=[many.pk]))
        self.assertEqual(len(q_many.captured_queries), len(q_one.captured_queries))

    def test_detail_returns_404_for_pending(self):
        response = self.client.get(reverse("competition_detail", args=[self.pending.pk]))
        self.assertEqual(response.status_code, 404)

    def test_token_hidden_from_anonymous(self):
        response = self.client.get(self.url)
        self.assertNotIn(self._token(), response.content.decode())

    def test_token_hidden_from_participant_non_owner(self):
        other = _make_user("other@example.com", User.Role.PARTICIPANT)
        self.client.force_login(other)
        response = self.client.get(self.url)
        self.assertNotIn(self._token(), response.content.decode())

    def test_token_visible_to_submitted_by(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertIn(self._token(), response.content.decode())

    def test_token_hidden_from_unrelated_organizer(self):
        # An organizer who did NOT submit this competition must not see its upload token.
        organizer = _make_user("org@example.com", User.Role.ORGANIZER)
        self.client.force_login(organizer)
        response = self.client.get(self.url)
        self.assertNotIn(self._token(), response.content.decode())

    def test_registration_section_precedes_comments(self):
        # With registration enabled, the registration block must render right after the
        # description/links, before the comments section (not below it).
        comp = _make_competition("RegOrder", status=Competition.Status.APPROVED, registration_enabled=True)
        content = self.client.get(reverse("competition_detail", args=[comp.pk])).content.decode()
        reg_pos = content.index(reverse("registrations:participant_list", args=[comp.pk]))
        comments_pos = content.index('id="comments"')
        self.assertLess(reg_pos, comments_pos)

    def test_token_visible_to_organizer_who_submitted(self):
        # An organizer who submitted the competition sees its upload token.
        submitter = _make_user("submitter_org@example.com", User.Role.ORGANIZER)
        comp = _make_competition("Org Submitted", status=Competition.Status.APPROVED, submitted_by=submitter)
        self.client.force_login(submitter)
        response = self.client.get(reverse("competition_detail", args=[comp.pk]))
        self.assertIn(str(comp.upload_token), response.content.decode())

    def test_token_visible_to_admin_who_did_not_submit(self):
        admin = _make_user("admin@example.com", User.Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertIn(self._token(), response.content.decode())

    def test_token_visible_to_superuser(self):
        superuser = User.objects.create_superuser(
            username="super@example.com", email="super@example.com", password="pw"
        )
        self.client.force_login(superuser)
        response = self.client.get(self.url)
        self.assertIn(self._token(), response.content.decode())

    def test_location_with_coords_adds_context_variables(self):
        from locations.models import Location

        loc = Location.add_root(name_ru="Velodrome", name_en="Velodrome", lat="43.238949", lng="76.889709")
        comp = _make_competition("Mapped Race", location=loc)
        response = self.client.get(reverse("competition_detail", args=[comp.pk]))
        self.assertIn("location_lat", response.context)
        self.assertIn("location_lng", response.context)
        self.assertIn("location_lat_display", response.context)
        self.assertIn("location_lng_display", response.context)
        self.assertContains(response, "competition-map")
        self.assertContains(response, "43.238949")

    def test_location_without_coords_omits_map(self):
        from locations.models import Location

        loc = Location.add_root(name_ru="Country", name_en="Country")
        comp = _make_competition("No Coords Race", location=loc)
        response = self.client.get(reverse("competition_detail", args=[comp.pk]))
        self.assertNotIn("location_lat", response.context)
        self.assertNotContains(response, "competition-map")

    def test_coordless_venue_falls_back_to_ancestor_coords(self):
        # A venue may be the hidden "other location" placeholder with no coordinates of its own;
        # the map/lat-lng must fall back to the nearest ancestor (here the city) so it still renders.
        from locations.models import Location

        country = Location.add_root(name_ru="China", name_en="China", lat="34.541225", lng="108.923707")
        region = country.add_child(name_ru="Inner Mongolia", name_en="Inner Mongolia")
        city = region.add_child(name_ru="West Ujimqin", name_en="West Ujimqin", lat="44.580860", lng="117.610187")
        other = city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
        self.assertIsNone(other.lat)
        comp = _make_competition("Steppe Race", location=other)
        response = self.client.get(reverse("competition_detail", args=[comp.pk]))
        self.assertContains(response, "competition-map")
        # falls back to the city pin, not the region/country
        self.assertEqual(response.context["location_lat"], "44.580860")
        self.assertEqual(response.context["location_lng"], "117.610187")

    def test_no_location_omits_map(self):
        response = self.client.get(self.url)
        self.assertNotIn("location_lat", response.context)
        self.assertNotContains(response, "competition-map")

    def test_positive_coords_show_abs_value_without_sign(self):
        from locations.models import Location

        loc = Location.add_root(name_ru="NE", name_en="NE", lat="43.238949", lng="76.889709")
        comp = _make_competition("NE Race", location=loc)
        response = self.client.get(reverse("competition_detail", args=[comp.pk]))
        self.assertIn("43.238949\u00b0", response.context["location_lat_display"])
        self.assertIn("76.889709\u00b0", response.context["location_lng_display"])
        self.assertNotIn("-", response.context["location_lat_display"])
        self.assertNotIn("-", response.context["location_lng_display"])

    def test_negative_coords_show_abs_value_and_different_direction_from_positive(self):
        from locations.models import Location

        south = Location.add_root(name_ru="SW", name_en="SW", lat="-33.868820", lng="-70.676150")
        north = Location.add_root(name_ru="NE", name_en="NE", lat="33.868820", lng="70.676150")
        comp_s = _make_competition("SW Race", location=south)
        comp_n = _make_competition("NE Race", location=north)
        resp_s = self.client.get(reverse("competition_detail", args=[comp_s.pk]))
        resp_n = self.client.get(reverse("competition_detail", args=[comp_n.pk]))
        # absolute value shown, no minus sign
        self.assertIn("33.868820\u00b0", resp_s.context["location_lat_display"])
        self.assertNotIn("-", resp_s.context["location_lat_display"])
        self.assertIn("70.676150\u00b0", resp_s.context["location_lng_display"])
        self.assertNotIn("-", resp_s.context["location_lng_display"])
        # direction label differs between south and north, west and east
        self.assertNotEqual(resp_s.context["location_lat_display"], resp_n.context["location_lat_display"])
        self.assertNotEqual(resp_s.context["location_lng_display"], resp_n.context["location_lng_display"])


class SubmitCompetitionViewTests(TestCase):
    def setUp(self):
        self.participant = _make_user("participant@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("organizer@example.com", User.Role.ORGANIZER)
        self.guest = _make_user("guest@example.com", User.Role.GUEST)

    def _submit_url(self):
        return reverse("calendar_submit")

    def _payload(self, **kwargs):
        data = {
            "title_ru": "My Race",
            "date_start": "2026-09-01",
        }
        data.update(kwargs)
        return data

    def test_participant_submit_creates_pending(self):
        self.client.login(username="participant@example.com", password="password123")
        self.client.post(self._submit_url(), self._payload())
        comp = Competition.objects.get(title_ru="My Race")
        self.assertEqual(comp.status, Competition.Status.PENDING_APPROVAL)
        self.assertEqual(comp.submitted_by, self.participant)

    def test_organizer_submit_creates_approved(self):
        self.client.login(username="organizer@example.com", password="password123")
        self.client.post(self._submit_url(), self._payload(title_ru="Organizer Race"))
        comp = Competition.objects.get(title_ru="Organizer Race")
        self.assertEqual(comp.status, Competition.Status.APPROVED)
        self.assertEqual(comp.approved_by, self.organizer)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self._submit_url(), self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_guest_redirected_to_profile(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(self._submit_url(), self._payload())
        self.assertRedirects(response, reverse("account_profile"))

    def test_invalid_date_range_shows_error(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(
            self._submit_url(),
            self._payload(date_start="2026-09-05", date_end="2026-09-01"),
            HTTP_ACCEPT_LANGUAGE="en",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], None, "End date cannot be before start date.")

    def test_date_range_error_translated_to_ru(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(
            self._submit_url(),
            self._payload(date_start="2026-09-05", date_end="2026-09-01"),
            HTTP_ACCEPT_LANGUAGE="ru",
        )
        self.assertEqual(response.status_code, 200)
        with translation_override("ru"):
            expected = gettext("End date cannot be before start date.")
        self.assertFormError(response.context["form"], None, expected)

    def test_get_shows_form(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(self._submit_url())
        self.assertEqual(response.status_code, 200)

    def test_file_route_accepts_zip(self):
        """Route/document uploads may be zip archives."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from calendar_app.forms import SubmitCompetitionForm

        upload = SimpleUploadedFile("route.zip", b"PK\x03\x04 dummy", content_type="application/zip")
        form = SubmitCompetitionForm(data=self._payload(), files={"file_route": upload}, user=self.participant)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("file_route", form.errors)

    def test_file_route_rejects_unsupported_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from calendar_app.forms import SubmitCompetitionForm

        upload = SimpleUploadedFile("route.exe", b"MZ dummy", content_type="application/octet-stream")
        form = SubmitCompetitionForm(data=self._payload(), files={"file_route": upload}, user=self.participant)
        self.assertFalse(form.is_valid())
        self.assertIn("file_route", form.errors)

    def test_title_max_length_error_uses_project_catalog_kk(self):
        """Regression: the shared mixin routes the title max_length error through the project
        catalog so the KK tab shows Kazakh, not Django's Russian fallback."""
        from calendar_app.forms import SubmitCompetitionForm

        with translation_override("kk"):
            form = SubmitCompetitionForm(
                data={"title_ru": "x" * 256, "date_start": "2026-09-01"}, user=self.participant
            )
            self.assertFalse(form.is_valid())
            expected = gettext("Ensure this value has at most %(limit_value)d characters.") % {"limit_value": 255}
            self.assertIn(expected, str(form.errors["title_ru"]))


class ModerationViewTests(TestCase):
    def setUp(self):
        self.participant = _make_user("participant@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("organizer@example.com", User.Role.ORGANIZER)
        self.comp = _make_competition("Pending", status=Competition.Status.PENDING_APPROVAL)

    def test_organizer_can_access_moderation(self):
        self.client.login(username="organizer@example.com", password="password123")
        response = self.client.get(reverse("calendar_moderate"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.comp, response.context["competitions"])

    def test_participant_gets_403(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(reverse("calendar_moderate"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("calendar_moderate"))
        self.assertEqual(response.status_code, 302)


class DisciplineCategoryModelTests(TestCase):
    def test_str(self):
        cat = DisciplineCategory.objects.create(name_ru="Road Cycling")
        self.assertEqual(str(cat), "Road Cycling")

    def test_ordering_by_order_field(self):
        cat_z = DisciplineCategory.objects.create(name_ru="Z Category", order=200)
        cat_a = DisciplineCategory.objects.create(name_ru="A Category", order=100)
        pks = list(DisciplineCategory.objects.filter(pk__in=[cat_a.pk, cat_z.pk]).values_list("pk", flat=True))
        self.assertEqual(pks, [cat_a.pk, cat_z.pk])


class CalendarDirectionFilterTests(TestCase):
    def setUp(self):
        self.road_cat = DisciplineCategory.objects.create(name_ru="Road", order=1)
        self.mtb_cat = DisciplineCategory.objects.create(name_ru="MTB", order=2)
        self.road_disc = Discipline.objects.create(name_ru="Road Race", category=self.road_cat, order=1)
        self.mtb_disc = Discipline.objects.create(name_ru="XCO", category=self.mtb_cat, order=1)
        self.road_comp = _make_competition(
            "Road Race Event",
            status=Competition.Status.APPROVED,
            date_start=datetime.date(2026, 9, 1),
            disciplines=[self.road_disc],
        )
        self.mtb_comp = _make_competition(
            "MTB Race Event",
            status=Competition.Status.APPROVED,
            date_start=datetime.date(2026, 9, 1),
            disciplines=[self.mtb_disc],
        )

    def test_direction_filter_on_api(self):
        response = self.client.get(
            reverse("calendar_events_api"),
            {"direction": self.road_cat.pk},
        )
        data = json.loads(response.content)
        titles = [e["title"] for e in data]
        self.assertIn("Road Race Event", titles)
        self.assertNotIn("MTB Race Event", titles)

    def test_direction_and_discipline_filters_are_ored(self):
        """A whole direction picked alongside another direction's discipline keeps both: an event
        matches if it has a selected discipline OR a discipline in a selected direction."""
        response = self.client.get(
            reverse("calendar_events_api"),
            {"direction": self.road_cat.pk, "discipline": self.mtb_disc.pk},
        )
        titles = [e["title"] for e in json.loads(response.content)]
        self.assertIn("Road Race Event", titles)  # matched by the road direction
        self.assertIn("MTB Race Event", titles)  # matched by the mtb discipline

    def test_direction_filter_on_list_view(self):
        response = self.client.get(
            reverse("calendar_list"),
            {
                "discipline_category": self.road_cat.pk,
                "date_from": "2026-09-01",
                "date_to": "2026-09-30",
            },
        )
        titles = [c.title for c in response.context["competitions"]]
        self.assertIn("Road Race Event", titles)
        self.assertNotIn("MTB Race Event", titles)


class SubmitViewDisciplineContextTests(TestCase):
    def setUp(self):
        self.participant = _make_user("participant@example.com", User.Role.PARTICIPANT)
        self.category = DisciplineCategory.objects.create(name_ru="Road", order=1)
        Discipline.objects.create(name_ru="Road Race", category=self.category, order=1)

    def test_submit_view_has_discipline_context(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse("calendar_submit"))
        self.assertIn("discipline_categories_json", response.context)
        self.assertIn("disciplines_json", response.context)
        cat_pks = [c["pk"] for c in response.context["discipline_categories_json"]]
        self.assertIn(self.category.pk, cat_pks)
        disc_cat_ids = [d["category_id"] for d in response.context["disciplines_json"]]
        self.assertIn(self.category.pk, disc_cat_ids)


class ListViewDisciplineContextTests(TestCase):
    def setUp(self):
        self.category = DisciplineCategory.objects.create(name_ru="Road", order=1)
        self.discipline = Discipline.objects.create(name_ru="Road Race", category=self.category, order=1)

    def test_list_view_has_discipline_context(self):
        response = self.client.get(reverse("calendar_list"))
        self.assertIn("discipline_categories", response.context)
        self.assertIn("disciplines_json", response.context)
        cat_pks = [c.pk for c in response.context["discipline_categories"]]
        self.assertIn(self.category.pk, cat_pks)
        disc_pks = [d["pk"] for d in response.context["disciplines_json"]]
        self.assertIn(self.discipline.pk, disc_pks)


class PickerLocaleFallbackTests(TestCase):
    """The picker JSON helpers must resolve names with the modeltranslation fallback (ru->en->kk).
    A blank translation would render empty options that the cascade merges into one checkbox,
    binding unrelated disciplines/directions together."""

    def test_disciplines_use_fallback_when_translation_missing(self):
        from calendar_app.views import _disciplines_for_locale

        cat = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", name_kk="")
        d1 = Discipline.objects.create(name_ru="Road Race", name_en="Road Race", name_kk="", category=cat)
        d2 = Discipline.objects.create(name_ru="Crit", name_en="Crit", name_kk="", category=cat)
        with translation_override("kk"):
            names = {r["pk"]: r["name"] for r in _disciplines_for_locale()}
        self.assertEqual(names[d1.pk], "Road Race")
        self.assertEqual(names[d2.pk], "Crit")
        self.assertNotEqual(names[d1.pk], names[d2.pk])  # distinct => the cascade keeps them separate

    def test_categories_use_fallback_when_translation_missing(self):
        from calendar_app.views import _categories_for_locale

        c1 = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", name_kk="")
        c2 = DisciplineCategory.objects.create(name_ru="MTB", name_en="MTB", name_kk="")
        with translation_override("kk"):
            names = {r["pk"]: r["name"] for r in _categories_for_locale()}
        self.assertEqual(names[c1.pk], "Road")
        self.assertEqual(names[c2.pk], "MTB")


class DisciplineCategoryRequiredTests(TestCase):
    """Every discipline must belong to a direction: the category FK is mandatory and a category that
    is in use cannot be deleted (PROTECT)."""

    def test_discipline_requires_a_category(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Discipline.objects.create(name_ru="No direction")

    def test_category_in_use_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        cat = DisciplineCategory.objects.create(name_ru="Road")
        Discipline.objects.create(name_ru="Road Race", category=cat)
        with self.assertRaises(ProtectedError):
            cat.delete()


class ApproveCompetitionViewTests(TestCase):
    def setUp(self):
        self.organizer = _make_user("organizer@example.com", User.Role.ORGANIZER)
        self.participant = _make_user("participant@example.com", User.Role.PARTICIPANT)
        self.comp = _make_competition("Pending", status=Competition.Status.PENDING_APPROVAL)

    def test_organizer_can_approve(self):
        self.client.login(username="organizer@example.com", password="password123")
        self.client.post(reverse("competition_approve", args=[self.comp.pk]))
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, Competition.Status.APPROVED)

    def test_participant_cannot_approve(self):
        self.client.login(username="participant@example.com", password="password123")
        self.client.post(reverse("competition_approve", args=[self.comp.pk]))
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, Competition.Status.PENDING_APPROVAL)

    def test_cannot_approve_non_pending(self):
        approved = _make_competition("Already approved", status=Competition.Status.APPROVED)
        self.client.login(username="organizer@example.com", password="password123")
        response = self.client.post(reverse("competition_approve", args=[approved.pk]))
        self.assertEqual(response.status_code, 404)


class RejectCompetitionViewTests(TestCase):
    def setUp(self):
        self.organizer = _make_user("organizer@example.com", User.Role.ORGANIZER)
        self.comp = _make_competition("Pending", status=Competition.Status.PENDING_APPROVAL)

    def test_organizer_can_reject_with_reason(self):
        self.client.login(username="organizer@example.com", password="password123")
        self.client.post(
            reverse("competition_reject", args=[self.comp.pk]),
            {"rejection_reason": "Too similar to another event"},
        )
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, Competition.Status.REJECTED)
        self.assertEqual(self.comp.rejection_reason, "Too similar to another event")

    def test_organizer_can_reject_without_reason(self):
        self.client.login(username="organizer@example.com", password="password123")
        self.client.post(reverse("competition_reject", args=[self.comp.pk]), {})
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, Competition.Status.REJECTED)


class CompetitionIsRegistrationOpenTests(TestCase):
    def _make_open_comp(self):
        return Competition.objects.create(
            title_ru="Open Race",
            date_start=datetime.date(2026, 7, 1),
            status=Competition.Status.APPROVED,
            registration_enabled=True,
        )

    def test_open_when_enabled_and_approved(self):
        comp = self._make_open_comp()
        self.assertTrue(comp.is_registration_open())

    def test_closed_when_disabled(self):
        comp = self._make_open_comp()
        comp.registration_enabled = False
        self.assertFalse(comp.is_registration_open())

    def test_closed_when_not_approved(self):
        comp = self._make_open_comp()
        comp.status = Competition.Status.PENDING_APPROVAL
        self.assertFalse(comp.is_registration_open())

    def test_closed_when_deadline_passed(self):
        comp = self._make_open_comp()
        comp.registration_deadline = timezone.now() - datetime.timedelta(days=1)
        self.assertFalse(comp.is_registration_open())

    def test_closed_when_deadline_earlier_today(self):
        # The deadline is a datetime: registration closes once the time of day has passed.
        comp = self._make_open_comp()
        comp.registration_deadline = timezone.now() - datetime.timedelta(hours=1)
        self.assertFalse(comp.is_registration_open())

    def test_open_when_deadline_later_today(self):
        comp = self._make_open_comp()
        comp.registration_deadline = timezone.now() + datetime.timedelta(hours=1)
        self.assertTrue(comp.is_registration_open())

    def test_deadline_field_parses_datetime_local_value(self):
        # The form field accepts the <input type="datetime-local"> value and keeps the time.
        from calendar_app.forms import RegistrationSettingsForm

        value = RegistrationSettingsForm().fields["registration_deadline"].clean("2026-09-01T14:30")
        self.assertEqual((value.year, value.month, value.day, value.hour, value.minute), (2026, 9, 1, 14, 30))

    def test_closed_when_overall_limit_reached(self):
        comp = self._make_open_comp()
        comp.max_participants = 1
        comp.save()
        from registrations.models import CompetitionRegistration

        CompetitionRegistration.objects.create(
            competition=comp,
            first_name="A",
            last_name="B",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
        )
        self.assertFalse(comp.is_registration_open())


class CompetitionQualifiedCountTests(TestCase):
    def setUp(self):
        self.comp = Competition.objects.create(
            title_ru="Count Race",
            date_start=datetime.date(2026, 7, 1),
            status=Competition.Status.APPROVED,
            registration_enabled=True,
        )

    def _make_reg(self, **kwargs):
        from registrations.models import CompetitionRegistration

        return CompetitionRegistration.objects.create(
            competition=self.comp,
            first_name="A",
            last_name="B",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
            **kwargs,
        )

    def test_counts_non_rejected_by_default(self):
        self._make_reg()
        self._make_reg()
        self._make_reg(is_rejected=True)
        self.assertEqual(self.comp.qualified_count(), 2)

    def test_require_approval_filters_unapproved(self):
        self.comp.require_approval = True
        self.comp.save()
        self._make_reg(is_approved=True)
        self._make_reg(is_approved=False)
        self.assertEqual(self.comp.qualified_count(), 1)

    def test_require_payment_filters_unpaid(self):
        self.comp.require_payment = True
        self.comp.save()
        self._make_reg(is_paid=True)
        self._make_reg(is_paid=False)
        self.assertEqual(self.comp.qualified_count(), 1)

    def test_both_require_flags(self):
        self.comp.require_approval = True
        self.comp.require_payment = True
        self.comp.save()
        self._make_reg(is_approved=True, is_paid=True)
        self._make_reg(is_approved=True, is_paid=False)
        self._make_reg(is_approved=False, is_paid=True)
        self.assertEqual(self.comp.qualified_count(), 1)


class CompetitionIsLimitReachedTests(TestCase):
    def setUp(self):
        self.comp = Competition.objects.create(
            title_ru="Limit Race",
            date_start=datetime.date(2026, 7, 1),
            status=Competition.Status.APPROVED,
        )

    def test_not_reached_with_no_limit(self):
        self.assertFalse(self.comp.is_limit_reached())

    def test_not_reached_below_limit(self):
        self.comp.max_participants = 5
        self.comp.save()
        self.assertFalse(self.comp.is_limit_reached())

    def test_reached_at_limit(self):
        self.comp.max_participants = 1
        self.comp.save()
        from registrations.models import CompetitionRegistration

        CompetitionRegistration.objects.create(
            competition=self.comp,
            first_name="A",
            last_name="B",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
        )
        self.assertTrue(self.comp.is_limit_reached())

    def test_per_category_limit(self):
        from registrations.models import CompetitionRegistration, RegistrationCategory

        cat = RegistrationCategory.objects.create(competition=self.comp, name="Elite", max_participants=1)
        CompetitionRegistration.objects.create(
            competition=self.comp,
            first_name="A",
            last_name="B",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
            category=cat,
        )
        self.assertTrue(self.comp.is_limit_reached(category=cat))


class SubmitCompetitionRegistrationTests(TestCase):
    def setUp(self):
        self.participant = _make_user("p_reg@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("o_reg@example.com", User.Role.ORGANIZER)
        self.url = reverse("calendar_submit")

    def _reg_payload(self):
        return {
            "title_ru": "Reg Race",
            "date_start": "2026-09-01",
            "registration_enabled": "on",
            "registration_mode": "free",
            "birth_date_mode": "year",
            "categories_json": "[]",
        }

    def test_participant_cannot_enable_registration(self):
        self.client.login(username="p_reg@example.com", password="password123")
        self.client.post(self.url, self._reg_payload())
        comp = Competition.objects.get(title_ru="Reg Race")
        self.assertFalse(comp.registration_enabled)

    def test_organizer_can_enable_registration(self):
        self.client.login(username="o_reg@example.com", password="password123")
        self.client.post(self.url, self._reg_payload())
        comp = Competition.objects.get(title_ru="Reg Race")
        self.assertTrue(comp.registration_enabled)

    def test_organizer_submit_locks_mode_on_first_enable(self):
        self.client.login(username="o_reg@example.com", password="password123")
        payload = self._reg_payload()
        payload["title_ru"] = "Lock Race"
        self.client.post(self.url, payload)
        comp = Competition.objects.get(title_ru="Lock Race")
        self.assertTrue(comp.registration_mode_locked)


class EditCompetitionViewTests(TestCase):
    def setUp(self):
        self.organizer = _make_user("edit_org@example.com", User.Role.ORGANIZER)
        self.other_org = _make_user("other_org@example.com", User.Role.ORGANIZER)
        self.participant = _make_user("edit_part@example.com", User.Role.PARTICIPANT)
        self.comp = _make_competition(
            "Editable Race",
            status=Competition.Status.APPROVED,
            submitted_by=self.organizer,
        )
        self.url = reverse("competition_edit", args=[self.comp.pk])

    def test_organizer_own_competition_can_access(self):
        self.client.login(username="edit_org@example.com", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_registration_deadline_prefilled_as_iso_under_ru_locale(self):
        # Regression: the registration_deadline input pre-fill was ru-localized, which
        # <input type=datetime-local> rejects. It must be ISO YYYY-MM-DDTHH:MM on the edit page.
        import re

        self.comp.registration_enabled = True
        self.comp.registration_deadline = timezone.make_aware(datetime.datetime(2026, 9, 1, 14, 30))
        self.comp.save()
        self.client.login(username="edit_org@example.com", password="password123")
        resp = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ru")
        m = re.search(r'name="registration_deadline"[^>]*value="([^"]*)"', resp.content.decode())
        self.assertEqual(m.group(1), "2026-09-01T14:30")

    def test_participant_gets_403(self):
        self.client.login(username="edit_part@example.com", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_organizer_of_other_competition_gets_403(self):
        self.client.login(username="other_org@example.com", password="password123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_edit_updates_title(self):
        self.client.login(username="edit_org@example.com", password="password123")
        self.client.post(
            self.url,
            {
                "title_ru": "Updated Title",
                "date_start": "2026-09-01",
                "registration_mode": "self_only",
                "birth_date_mode": "year",
                "categories_json": "[]",
            },
        )
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.title_ru, "Updated Title")

    def test_edit_updates_disciplines(self):
        cat = DisciplineCategory.objects.create(name_ru="Road", order=1)
        d1 = Discipline.objects.create(name_ru="Road Race", category=cat, order=1)
        d2 = Discipline.objects.create(name_ru="Gravel", category=cat, order=2)
        self.comp.disciplines.set([d1])
        self.client.login(username="edit_org@example.com", password="password123")
        self.client.post(
            self.url,
            {
                "title_ru": "Editable Race",
                "date_start": "2026-09-01",
                "disciplines": [str(d1.pk), str(d2.pk)],
                "registration_mode": "self_only",
                "birth_date_mode": "year",
                "categories_json": "[]",
            },
        )
        self.comp.refresh_from_db()
        self.assertEqual(set(self.comp.disciplines.values_list("pk", flat=True)), {d1.pk, d2.pk})

    def test_edit_prefills_current_disciplines_as_checked(self):
        cat = DisciplineCategory.objects.create(name_ru="Road", order=1)
        d1 = Discipline.objects.create(name_ru="Road Race", category=cat, order=1)
        self.comp.disciplines.set([d1])
        self.client.login(username="edit_org@example.com", password="password123")
        resp = self.client.get(self.url)
        self.assertIn(d1.pk, resp.context["selected_disciplines"])

    def test_mode_not_changed_when_locked(self):
        self.comp.registration_mode = "self_only"
        self.comp.registration_mode_locked = True
        self.comp.save()
        self.client.login(username="edit_org@example.com", password="password123")
        self.client.post(
            self.url,
            {
                "title_ru": "Editable Race",
                "date_start": "2026-09-01",
                "registration_enabled": "on",
                "registration_mode": "free",
                "birth_date_mode": "year",
                "categories_json": "[]",
            },
        )
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.registration_mode, "self_only")

    def test_edit_saves_registration_deadline_with_time(self):
        self.client.login(username="edit_org@example.com", password="password123")
        self.client.post(
            self.url,
            {
                "title_ru": "Editable Race",
                "date_start": "2026-09-01",
                "registration_enabled": "on",
                "registration_mode": "free",
                "birth_date_mode": "year",
                "registration_deadline": "2026-09-01T14:30",
                "categories_json": "[]",
            },
        )
        self.comp.refresh_from_db()
        self.assertIsNotNone(self.comp.registration_deadline)
        local = timezone.localtime(self.comp.registration_deadline)
        self.assertEqual((local.date(), local.hour, local.minute), (datetime.date(2026, 9, 1), 14, 30))

    @override_settings(TIME_ZONE="Asia/Almaty")
    def test_deadline_interpreted_in_business_timezone_not_utc(self):
        # Under a non-UTC business tz, datetime-local "14:30" is local wall time (Astana, UTC+5)
        # = 09:30 UTC, not 14:30 UTC -- the field must not be silently treated as UTC.
        self.client.login(username="edit_org@example.com", password="password123")
        self.client.post(
            self.url,
            {
                "title_ru": "Editable Race",
                "date_start": "2026-09-01",
                "registration_enabled": "on",
                "registration_mode": "free",
                "birth_date_mode": "year",
                "registration_deadline": "2026-09-01T14:30",
                "categories_json": "[]",
            },
        )
        self.comp.refresh_from_db()
        utc = self.comp.registration_deadline.astimezone(datetime.UTC)
        self.assertEqual((utc.hour, utc.minute), (9, 30))


class CompetitionCommentTests(TestCase):
    def setUp(self):
        self.participant = _make_user("commenter@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("comp_owner@example.com", User.Role.ORGANIZER)
        self.other_participant = _make_user("other@example.com", User.Role.PARTICIPANT)
        self.admin = _make_user("admin@example.com", User.Role.ADMIN)
        self.comp = _make_competition(
            "Comment Race",
            status=Competition.Status.APPROVED,
            submitted_by=self.organizer,
        )
        self.add_url = reverse("competition_add_comment", args=[self.comp.pk])

    def _add_comment(self, user, body="Great race!"):
        self.client.login(username=user.email, password="password123")
        return self.client.post(self.add_url, {"body": body})

    def _make_comment(self, author=None, body="A comment"):
        return CompetitionComment.objects.create(
            competition=self.comp,
            author=author or self.participant,
            body=body,
        )

    def test_participant_can_post_comment(self):
        self._add_comment(self.participant)
        self.assertEqual(CompetitionComment.objects.count(), 1)

    def test_comment_has_correct_author_and_competition(self):
        self._add_comment(self.participant)
        comment = CompetitionComment.objects.get()
        self.assertEqual(comment.author, self.participant)
        self.assertEqual(comment.competition, self.comp)

    def test_unauthenticated_user_redirected(self):
        response = self.client.post(self.add_url, {"body": "Hi"})
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(CompetitionComment.objects.count(), 0)

    def test_guest_role_redirected_to_profile(self):
        _make_user("guest@example.com", User.Role.GUEST)
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(self.add_url, {"body": "Hi"})
        self.assertRedirects(response, reverse("account_profile"))
        self.assertEqual(CompetitionComment.objects.count(), 0)

    def test_add_to_non_approved_competition_returns_404(self):
        pending = _make_competition("Pending", status=Competition.Status.PENDING_APPROVAL)
        url = reverse("competition_add_comment", args=[pending.pk])
        self.client.login(username=self.participant.email, password="password123")
        response = self.client.post(url, {"body": "Hi"})
        self.assertEqual(response.status_code, 404)

    def test_manager_can_delete_comment(self):
        comment = self._make_comment()
        delete_url = reverse("competition_delete_comment", args=[comment.pk])
        self.client.login(username=self.organizer.email, password="password123")
        self.client.post(delete_url)
        self.assertEqual(CompetitionComment.objects.count(), 0)

    def test_admin_can_delete_comment(self):
        comment = self._make_comment()
        delete_url = reverse("competition_delete_comment", args=[comment.pk])
        self.client.login(username=self.admin.email, password="password123")
        self.client.post(delete_url)
        self.assertEqual(CompetitionComment.objects.count(), 0)

    def test_non_manager_cannot_delete_comment(self):
        comment = self._make_comment(author=self.other_participant)
        delete_url = reverse("competition_delete_comment", args=[comment.pk])
        self.client.login(username=self.participant.email, password="password123")
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CompetitionComment.objects.count(), 1)

    def test_unauthenticated_cannot_delete(self):
        comment = self._make_comment()
        delete_url = reverse("competition_delete_comment", args=[comment.pk])
        response = self.client.post(delete_url)
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(CompetitionComment.objects.count(), 1)

    def test_anonymous_detail_does_not_expose_author_email(self):
        self._make_comment(body="Hi")  # author has no name set
        response = self.client.get(reverse("competition_detail", args=[self.comp.pk]))
        self.assertNotContains(response, self.participant.email)

    def test_comment_placeholder_localized(self):
        from django.utils.translation import gettext, override

        from calendar_app.forms import AddCompetitionCommentForm

        for loc in ("ru", "kk", "en"):
            with self.subTest(locale=loc), override(loc):
                self.assertIn(gettext("Write a comment..."), str(AddCompetitionCommentForm()))

    def test_delete_nonexistent_comment_returns_404(self):
        delete_url = reverse("competition_delete_comment", args=[99999])
        self.client.login(username=self.organizer.email, password="password123")
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 404)

    def test_comments_shown_on_detail_page(self):
        self._make_comment(body="Visible comment")
        response = self.client.get(reverse("competition_detail", args=[self.comp.pk]))
        self.assertContains(response, "Visible comment")

    def test_comment_newlines_preserved_on_detail_page(self):
        # The author's line breaks must survive to the output inside the pre-wrap container
        # (regression: HTML collapses raw newlines unless the comment-body class is applied).
        import re

        self._make_comment(body="line one\nline two")
        response = self.client.get(reverse("competition_detail", args=[self.comp.pk]))
        m = re.search(r'class="[^"]*comment-body[^"]*">(.*?)</p>', response.content.decode(), re.S)
        self.assertIsNotNone(m)
        self.assertIn("line one\nline two", m.group(1))


class CompetitionDirectionLocationLabelTests(TestCase):
    """Direction / country / region / city helper properties used by the list table."""

    def setUp(self):
        self.country = Location.add_root(name_ru="Kazakhstan", name_kk="Kazakhstan", name_en="Kazakhstan")
        self.region = self.country.add_child(name_ru="Almaty Region", name_kk="Almaty Region", name_en="Almaty Region")
        self.city = self.region.add_child(name_ru="Almaty", name_kk="Almaty", name_en="Almaty")
        self.venue = self.city.add_child(name_ru="Sokol", name_kk="Sokol", name_en="Sokol")
        self.category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road")
        self.discipline = Discipline.objects.create(name_ru="Road Race", name_en="Road Race", category=self.category)

    def test_labels_for_venue_location(self):
        comp = _make_competition("Venue race", location=self.venue, disciplines=[self.discipline])
        self.assertEqual(comp.direction_label, "Road")
        self.assertEqual(comp.country_label, "Kazakhstan")
        self.assertEqual(comp.region_label, "Almaty Region")
        self.assertEqual(comp.city_label, "Almaty")

    def test_labels_for_city_location(self):
        comp = _make_competition("City race", location=self.city, disciplines=[self.discipline])
        self.assertEqual(comp.country_label, "Kazakhstan")
        self.assertEqual(comp.region_label, "Almaty Region")
        self.assertEqual(comp.city_label, "Almaty")

    def test_region_location_has_no_city(self):
        comp = _make_competition("Region race", location=self.region)
        self.assertEqual(comp.country_label, "Kazakhstan")
        self.assertEqual(comp.region_label, "Almaty Region")
        self.assertEqual(comp.city_label, "")

    def test_labels_empty_without_location_or_discipline(self):
        comp = _make_competition("Bare race")
        self.assertEqual(comp.country_label, "")
        self.assertEqual(comp.region_label, "")
        self.assertEqual(comp.city_label, "")
        self.assertEqual(comp.direction_label, "")


class CompetitionListColumnsViewTests(TestCase):
    def test_list_shows_direction_country_region_city_columns(self):
        country = Location.add_root(name_ru="Kazakhstan", name_kk="Kazakhstan", name_en="Kazakhstan")
        region = country.add_child(name_ru="Almaty Region", name_kk="Almaty Region", name_en="Almaty Region")
        city = region.add_child(name_ru="Almaty", name_kk="Almaty", name_en="Almaty")
        category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road")
        discipline = Discipline.objects.create(name_ru="Road Race", name_en="Road Race", category=category)
        _make_competition(
            "Visible Race",
            location=city,
            disciplines=[discipline],
            date_start=timezone.localdate() + datetime.timedelta(days=3),
        )
        response = self.client.get(reverse("calendar_list"), HTTP_ACCEPT_LANGUAGE="en")
        # Multi-valued columns are pluralized; single-valued ones stay singular.
        for header in ("Type", "Directions", "Disciplines", "Country", "Region", "City", "Location"):
            self.assertContains(response, f"<th>{header}</th>")
        self.assertNotContains(response, "<th>Discipline</th>")
        self.assertContains(response, "Road")
        self.assertContains(response, "Kazakhstan")
        self.assertContains(response, "Almaty Region")


class MultiLocationFilterTests(TestCase):
    """Multi-select location filtering: union of descendants across selected nodes,
    with same-name nodes merged into one comma-joined value (issue #108)."""

    def setUp(self):
        # KZ > Almaty obl > Almaty > Venue A ; RU > Moscow obl > Moscow > Venue B
        self.kz = Location.add_root(name_ru="KZ", name_en="KZ")
        self.kz_obl = self.kz.add_child(name_ru="Almaty obl", name_en="Almaty obl")
        self.kz_city = self.kz_obl.add_child(name_ru="Almaty", name_en="Almaty")
        self.kz_venue = self.kz_city.add_child(name_ru="Venue A", name_en="Venue A")
        self.ru = Location.add_root(name_ru="RU", name_en="RU")
        self.ru_obl = self.ru.add_child(name_ru="Moscow obl", name_en="Moscow obl")
        self.ru_city = self.ru_obl.add_child(name_ru="Moscow", name_en="Moscow")
        self.ru_venue = self.ru_city.add_child(name_ru="Venue B", name_en="Venue B")
        self.comp_kz = _make_competition("KZ Race", location=self.kz_venue, date_start=datetime.date(2026, 7, 1))
        self.comp_ru = _make_competition("RU Race", location=self.ru_venue, date_start=datetime.date(2026, 7, 1))

    def test_helper_unions_descendants_of_multiple_ids(self):
        from calendar_app.views import _location_descendant_pks

        pks = _location_descendant_pks([self.kz.pk, self.ru.pk])
        self.assertIn(self.kz_venue.pk, pks)
        self.assertIn(self.ru_venue.pk, pks)

    def test_helper_splits_comma_joined_and_ignores_invalid(self):
        from calendar_app.views import _location_descendant_pks

        pks = _location_descendant_pks([f"{self.kz_obl.pk},{self.ru_obl.pk}", "not-an-int", ""])
        self.assertIn(self.kz_venue.pk, pks)
        self.assertIn(self.ru_venue.pk, pks)

    def test_events_api_filters_by_multiple_location_params(self):
        resp = self.client.get(reverse("calendar_events_api"), {"location": [self.kz.pk, self.ru.pk]})
        ids = {e["id"] for e in resp.json()}
        self.assertEqual(ids, {self.comp_kz.pk, self.comp_ru.pk})

    def test_events_api_single_country_excludes_other(self):
        resp = self.client.get(reverse("calendar_events_api"), {"location": [self.kz.pk]})
        ids = {e["id"] for e in resp.json()}
        self.assertEqual(ids, {self.comp_kz.pk})

    def test_events_api_comma_joined_value_filters_all_matching(self):
        # A merged same-name choice carries several ids as one comma-joined value.
        resp = self.client.get(reverse("calendar_events_api") + f"?location={self.kz_obl.pk},{self.ru_obl.pk}")
        ids = {e["id"] for e in resp.json()}
        self.assertEqual(ids, {self.comp_kz.pk, self.comp_ru.pk})

    def test_list_view_filters_by_multiple_locations(self):
        resp = self.client.get(
            reverse("calendar_list"),
            {"location": [self.kz.pk, self.ru.pk], "date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
        self.assertContains(resp, "KZ Race")
        self.assertContains(resp, "RU Race")

    def test_list_view_single_location_excludes_other(self):
        resp = self.client.get(
            reverse("calendar_list"),
            {"location": [self.ru.pk], "date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
        self.assertContains(resp, "RU Race")
        self.assertNotContains(resp, "KZ Race")


class MultiSelectIdFilterTests(TestCase):
    """Multi-select event-type / direction / discipline filtering (issue #108).

    Each filter accepts several ids via getlist; a value may be comma-joined (same-name
    nodes merged into one choice). Disciplines take priority over directions.
    """

    def setUp(self):
        self.race = EventType.objects.create(name_ru="Race", order=1)
        self.training = EventType.objects.create(name_ru="Training", order=2)
        self.festival = EventType.objects.create(name_ru="Festival", order=3)
        self.road = DisciplineCategory.objects.create(name_ru="Road", order=1)
        self.mtb = DisciplineCategory.objects.create(name_ru="MTB", order=2)
        self.run = DisciplineCategory.objects.create(name_ru="Run", order=3)
        self.road_disc = Discipline.objects.create(name_ru="Road Race", category=self.road, order=1)
        self.mtb_disc = Discipline.objects.create(name_ru="XCO", category=self.mtb, order=1)
        self.run_disc = Discipline.objects.create(name_ru="10k", category=self.run, order=1)
        # Same-name discipline under two categories -> merged choice carries both ids.
        self.road_relay = Discipline.objects.create(name_ru="Relay", category=self.road, order=2)
        self.mtb_relay = Discipline.objects.create(name_ru="Relay", category=self.mtb, order=2)
        d = datetime.date(2026, 9, 1)
        self.c_race_road = _make_competition(
            "Race Road", event_type=self.race, disciplines=[self.road_disc], date_start=d
        )
        self.c_train_mtb = _make_competition(
            "Train MTB", event_type=self.training, disciplines=[self.mtb_disc], date_start=d
        )
        self.c_fest_run = _make_competition(
            "Fest Run", event_type=self.festival, disciplines=[self.run_disc], date_start=d
        )
        self.c_road_relay = _make_competition("Road Relay", disciplines=[self.road_relay], date_start=d)
        self.c_mtb_relay = _make_competition("MTB Relay", disciplines=[self.mtb_relay], date_start=d)

    def _api_titles(self, params):
        return {e["title"] for e in self.client.get(reverse("calendar_events_api"), params).json()}

    def _list(self, params):
        params = {**params, "date_from": "2026-09-01", "date_to": "2026-09-30"}
        return self.client.get(reverse("calendar_list"), params)

    def test_helper_parses_comma_joined_and_ignores_junk(self):
        from calendar_app.views import _parse_int_ids

        self.assertEqual(_parse_int_ids(["1,2", "3", "x", ""]), {1, 2, 3})

    def test_multiple_event_types(self):
        self.assertEqual(self._api_titles({"event_type": [self.race.pk, self.festival.pk]}), {"Race Road", "Fest Run"})

    def test_multiple_directions(self):
        titles = self._api_titles({"direction": [self.road.pk, self.mtb.pk]})
        self.assertEqual(titles, {"Race Road", "Train MTB", "Road Relay", "MTB Relay"})

    def test_multiple_disciplines(self):
        self.assertEqual(
            self._api_titles({"discipline": [self.road_disc.pk, self.run_disc.pk]}), {"Race Road", "Fest Run"}
        )

    def test_comma_joined_direction_value_filters_all(self):
        resp = self.client.get(reverse("calendar_events_api") + f"?direction={self.road.pk},{self.mtb.pk}")
        titles = {e["title"] for e in resp.json()}
        self.assertNotIn("Fest Run", titles)
        self.assertIn("Race Road", titles)
        self.assertIn("Train MTB", titles)

    def test_comma_joined_discipline_value_filters_merged_same_name(self):
        resp = self.client.get(reverse("calendar_events_api") + f"?discipline={self.road_relay.pk},{self.mtb_relay.pk}")
        self.assertEqual({e["title"] for e in resp.json()}, {"Road Relay", "MTB Relay"})

    def test_direction_and_discipline_ored_with_multi(self):
        # direction=[Road] OR discipline=[XCO]: all Road events plus the MTB XCO event.
        self.assertEqual(
            self._api_titles({"direction": [self.road.pk], "discipline": [self.mtb_disc.pk]}),
            {"Race Road", "Road Relay", "Train MTB"},
        )

    def test_invalid_value_is_ignored_not_emptied(self):
        titles = self._api_titles({"event_type": ["not-an-int"]})
        self.assertIn("Race Road", titles)
        self.assertIn("Train MTB", titles)

    def test_list_view_multiple_event_types(self):
        resp = self._list({"event_type": [self.race.pk, self.festival.pk]})
        self.assertContains(resp, "Race Road")
        self.assertContains(resp, "Fest Run")
        self.assertNotContains(resp, "Train MTB")

    def test_list_view_multiple_directions(self):
        resp = self._list({"discipline_category": [self.road.pk, self.run.pk]})
        self.assertContains(resp, "Race Road")
        self.assertContains(resp, "Fest Run")
        self.assertNotContains(resp, "Train MTB")

    def test_list_view_multiple_disciplines(self):
        resp = self._list({"discipline": [self.mtb_disc.pk, self.run_disc.pk]})
        self.assertContains(resp, "Train MTB")
        self.assertContains(resp, "Fest Run")
        self.assertNotContains(resp, "Race Road")


class MultiDisciplinePerCompetitionTests(TestCase):
    """A single competition can carry several disciplines (and thus directions); filters
    match if it has at least one selected discipline/direction (#multi-discipline)."""

    def setUp(self):
        self.road = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", order=1)
        self.gravel = DisciplineCategory.objects.create(name_ru="Gravel", name_en="Gravel", order=2)
        self.mtb = DisciplineCategory.objects.create(name_ru="MTB", name_en="MTB", order=3)
        self.road_disc = Discipline.objects.create(name_ru="Road Race", name_en="Road Race", category=self.road)
        self.gravel_disc = Discipline.objects.create(name_ru="Gravel Race", name_en="Gravel Race", category=self.gravel)
        self.mtb_disc = Discipline.objects.create(name_ru="XCO", name_en="XCO", category=self.mtb)
        d = datetime.date(2026, 9, 1)
        # One event bound to two disciplines across two directions.
        self.multi = _make_competition(
            "Road+Gravel Fondo", disciplines=[self.road_disc, self.gravel_disc], date_start=d
        )
        self.mtb_only = _make_competition("MTB Marathon", disciplines=[self.mtb_disc], date_start=d)

    def _api_titles(self, params):
        return {e["title"] for e in self.client.get(reverse("calendar_events_api"), params).json()}

    def test_labels_join_all_disciplines_and_distinct_directions(self):
        self.assertEqual(self.multi.disciplines_label, "Road Race, Gravel Race")
        self.assertEqual(self.multi.direction_label, "Road, Gravel")

    def test_matches_when_any_discipline_selected(self):
        self.assertEqual(self._api_titles({"discipline": self.road_disc.pk}), {"Road+Gravel Fondo"})
        self.assertEqual(self._api_titles({"discipline": self.gravel_disc.pk}), {"Road+Gravel Fondo"})

    def test_matches_when_any_direction_selected(self):
        self.assertEqual(self._api_titles({"direction": self.road.pk}), {"Road+Gravel Fondo"})
        self.assertEqual(self._api_titles({"direction": self.gravel.pk}), {"Road+Gravel Fondo"})

    def test_not_matched_by_unrelated_discipline_or_direction(self):
        self.assertNotIn("Road+Gravel Fondo", self._api_titles({"discipline": self.mtb_disc.pk}))
        self.assertNotIn("Road+Gravel Fondo", self._api_titles({"direction": self.mtb.pk}))

    def test_multi_discipline_event_listed_once_per_filter(self):
        """The many-to-many join must be de-duplicated when several selected ids match."""
        titles = [
            e["title"]
            for e in self.client.get(
                reverse("calendar_events_api"),
                {"direction": [self.road.pk, self.gravel.pk]},
            ).json()
        ]
        self.assertEqual(titles.count("Road+Gravel Fondo"), 1)


class CompetitionAdminCategoryFilterTests(TestCase):
    """Wagtail admin: filtering by direction (category) must not duplicate a competition that has
    several disciplines of that category - the M2M-spanning filter needs distinct()."""

    def test_category_filter_dedups_multi_discipline_competition(self):
        from calendar_app.wagtail_hooks import CompetitionFilterSet

        cat = DisciplineCategory.objects.create(name_ru="Road")
        d1 = Discipline.objects.create(name_ru="Road Race", category=cat)
        d2 = Discipline.objects.create(name_ru="Crit", category=cat)
        comp = _make_competition("Two of one category", disciplines=[d1, d2])
        fs = CompetitionFilterSet(data={"disciplines__category": str(cat.pk)}, queryset=Competition.objects.all())
        ids = list(fs.qs.values_list("pk", flat=True))
        self.assertEqual(ids.count(comp.pk), 1)
        self.assertEqual(len(ids), len(set(ids)))

    def test_viewset_uses_the_deduping_filterset(self):
        from calendar_app.wagtail_hooks import CompetitionFilterSet, CompetitionViewSet

        self.assertIs(CompetitionViewSet.filterset_class, CompetitionFilterSet)


class CompetitionAdminListQueryTests(TestCase):
    """The Wagtail admin index queryset must prefetch disciplines so disciplines_label (in
    list_display) does not issue one query per row."""

    def test_index_queryset_prefetches_disciplines(self):
        from calendar_app.wagtail_hooks import CompetitionViewSet

        cat = DisciplineCategory.objects.create(name_ru="Road")
        discs = [Discipline.objects.create(name_ru=f"D{i}", category=cat, order=i) for i in range(3)]
        for i in range(3):
            _make_competition(f"Row {i}", disciplines=discs)
        viewset = CompetitionViewSet()
        # 1 query for the competitions + 1 for the prefetched disciplines, regardless of row count
        # (without the prefetch this is 1 + N, i.e. 4 here).
        with self.assertNumQueries(2):
            labels = [c.disciplines_label for c in viewset.get_queryset(None)]
        self.assertTrue(all(labels))


class CalendarMapViewTests(TestCase):
    """Map view page + the 3-button calendar/list/map switcher (issue #107)."""

    def test_map_returns_200(self):
        self.assertEqual(self.client.get(reverse("calendar_map")).status_code, 200)

    def test_map_has_context(self):
        response = self.client.get(reverse("calendar_map"))
        for key in ("date_from", "date_to", "event_types_json", "categories_json", "disciplines_json"):
            self.assertIn(key, response.context)

    def test_map_has_three_view_switch_links(self):
        response = self.client.get(reverse("calendar_map"))
        for view_id in ("view-link-calendar", "view-link-list", "view-link-map"):
            self.assertContains(response, view_id)

    def test_list_and_calendar_pages_carry_the_switcher(self):
        for url_name in ("calendar", "calendar_list"):
            response = self.client.get(reverse(url_name))
            self.assertContains(response, "view-link-map")


class CalendarMapAPIViewTests(TestCase):
    """Map API: locations with coordinates that have competitions matching the filters."""

    def setUp(self):
        self.cat = DisciplineCategory.objects.create(name_ru="Road", order=1)
        self.disc = Discipline.objects.create(name_ru="Road Race", category=self.cat, order=1)
        self.event_type = EventType.objects.create(name_ru="Race", order=1)
        self.loc = Location.add_root(name_ru="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709")
        self.loc_nocoords = Location.add_root(name_ru="NoCoords", name_en="NoCoords")
        self.comp = _make_competition(
            "Mapped Race",
            location=self.loc,
            disciplines=[self.disc],
            event_type=self.event_type,
            date_start=datetime.date(2026, 7, 10),
        )
        _make_competition("Unmapped", location=self.loc_nocoords, date_start=datetime.date(2026, 7, 10))
        _make_competition("NoLoc", date_start=datetime.date(2026, 7, 10))
        _make_competition(
            "Pending",
            status=Competition.Status.PENDING_APPROVAL,
            location=self.loc,
            date_start=datetime.date(2026, 7, 10),
        )

    def _data(self, params=None):
        return self.client.get(reverse("calendar_map_api"), params or {}).json()

    def _group(self, data):
        return next(g for g in data if g["location_id"] == self.loc.pk)

    def test_only_locations_with_coords_and_approved_matches(self):
        data = self._data()
        ids = {g["location_id"] for g in data}
        self.assertIn(self.loc.pk, ids)
        self.assertNotIn(self.loc_nocoords.pk, ids)  # no coordinates
        titles = {c["title"] for c in self._group(data)["competitions"]}
        self.assertIn("Mapped Race", titles)
        self.assertNotIn("Pending", titles)  # not approved

    def test_marker_carries_coords_and_competition_link(self):
        group = self._group(self._data())
        self.assertAlmostEqual(group["lat"], 43.238949, places=5)
        self.assertAlmostEqual(group["lng"], 76.889709, places=5)
        comp = group["competitions"][0]
        self.assertIn(f"/calendar/{self.comp.pk}/", comp["url"])
        self.assertEqual(comp["date_start"], "2026-07-10")

    def test_event_type_filter(self):
        other = EventType.objects.create(name_ru="Training", order=2)
        self.assertEqual(self._data({"event_type": other.pk}), [])
        self.assertTrue(self._data({"event_type": self.event_type.pk}))

    def test_direction_filter(self):
        self.assertTrue(self._data({"direction": self.cat.pk}))
        other = DisciplineCategory.objects.create(name_ru="MTB", order=2)
        self.assertEqual(self._data({"direction": other.pk}), [])

    def test_date_range_filter(self):
        self.assertEqual(self._data({"date_from": "2026-07-01", "date_to": "2026-07-05"}), [])
        self.assertTrue(self._data({"date_from": "2026-07-01", "date_to": "2026-07-31"}))

    def test_groups_multiple_competitions_at_one_location(self):
        _make_competition("Second Race", location=self.loc, date_start=datetime.date(2026, 7, 12))
        self.assertEqual(len(self._group(self._data())["competitions"]), 2)

    def test_hidden_competition_excluded_for_anonymous(self):
        _make_competition("Hidden Race", location=self.loc, is_hidden=True, date_start=datetime.date(2026, 7, 11))
        titles = {c["title"] for c in self._group(self._data())["competitions"]}
        self.assertNotIn("Hidden Race", titles)


class CalendarMapResolutionTests(TestCase):
    """A competition at a hidden/coordinate-less venue is shown on the calendar map at the
    nearest ancestor with coordinates, labelled with that ancestor's name (issue #113)."""

    def setUp(self):
        self.country = Location.add_root(name_ru="KZ", name_en="KZ", lat="48.000000", lng="68.000000")
        self.region = self.country.add_child(name_ru="Region", name_en="Region", lat="49.000000", lng="69.000000")
        self.city = self.region.add_child(name_ru="Almaty", name_en="Almaty", lat="43.200000", lng="76.900000")

    def _data(self, params=None):
        return self.client.get(reverse("calendar_map_api"), params or {}).json()

    def test_hidden_venue_resolves_to_city_not_its_own_coords(self):
        # The hidden venue carries its own (placeholder) coords; the marker must use the city's.
        other = self.city.add_child(
            name_ru="Other location", name_en="Other location", is_hidden=True, lat="11.111111", lng="22.222222"
        )
        _make_competition("Race", location=other, date_start=datetime.date(2026, 7, 10))
        data = self._data()
        self.assertEqual(len(data), 1)
        group = data[0]
        self.assertEqual(group["location_id"], self.city.pk)
        self.assertEqual(group["name"], "Almaty")
        self.assertAlmostEqual(group["lat"], 43.2, places=5)
        self.assertEqual({c["title"] for c in group["competitions"]}, {"Race"})

    def test_hidden_venue_falls_back_to_region_when_city_has_no_coords(self):
        city2 = self.region.add_child(name_ru="NoCoordCity", name_en="NoCoordCity")
        other = city2.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
        _make_competition("R2", location=other, date_start=datetime.date(2026, 7, 10))
        groups = {g["location_id"]: g for g in self._data()}
        self.assertIn(self.region.pk, groups)
        self.assertNotIn(city2.pk, groups)
        self.assertEqual(groups[self.region.pk]["name"], "Region")

    def test_venue_with_own_coords_stays_at_venue(self):
        venue = self.city.add_child(name_ru="Velodrome", name_en="Velodrome", lat="43.300000", lng="77.000000")
        _make_competition("VRace", location=venue, date_start=datetime.date(2026, 7, 10))
        groups = {g["location_id"]: g for g in self._data()}
        self.assertIn(venue.pk, groups)
        self.assertAlmostEqual(groups[venue.pk]["lat"], 43.3, places=5)

    def test_multiple_hidden_venue_competitions_group_under_one_city_marker(self):
        other = self.city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
        _make_competition("A", location=other, date_start=datetime.date(2026, 7, 10))
        _make_competition("B", location=other, date_start=datetime.date(2026, 7, 12))
        groups = {g["location_id"]: g for g in self._data()}
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[self.city.pk]["competitions"]), 2)

    def test_unresolvable_venue_is_skipped(self):
        country = Location.add_root(name_ru="NoWhere", name_en="NoWhere")
        region = country.add_child(name_ru="NR", name_en="NR")
        city = region.add_child(name_ru="NC", name_en="NC")
        other = city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
        _make_competition("Ghost", location=other, date_start=datetime.date(2026, 7, 10))
        self.assertEqual(self._data(), [])

    def test_hidden_ancestor_with_coords_is_skipped(self):
        # A hidden city must never be a marker even if it carries coordinates: resolve up.
        hidden_city = self.region.add_child(
            name_ru="HiddenCity", name_en="HiddenCity", is_hidden=True, lat="50.000000", lng="50.000000"
        )
        other = hidden_city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
        _make_competition("HRace", location=other, date_start=datetime.date(2026, 7, 10))
        groups = {g["location_id"]: g for g in self._data()}
        self.assertIn(self.region.pk, groups)
        self.assertNotIn(hidden_city.pk, groups)
        self.assertEqual(groups[self.region.pk]["name"], "Region")

    def test_deleted_location_competition_is_excluded(self):
        venue = self.city.add_child(name_ru="DeadVenue", name_en="DeadVenue", lat="43.300000", lng="77.000000")
        _make_competition("DeadRace", location=venue, date_start=datetime.date(2026, 7, 10))
        venue.is_deleted = True
        venue.save(update_fields=["is_deleted"])
        self.assertEqual(self._data(), [])


class LocationProposalInSubmitTests(TestCase):
    """Proposing a venue while submitting a competition (issue #111)."""

    def setUp(self):
        self.participant = _make_user("p_loc@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("o_loc@example.com", User.Role.ORGANIZER)
        self.country = Location.add_root(name_ru="KZ", name_en="KZ")
        self.region = self.country.add_child(name_ru="Region", name_en="Region")
        self.city = self.region.add_child(name_ru="City", name_en="City")

    def _payload(self, **kw):
        data = {
            "title_ru": "Race",
            "date_start": "2026-09-01",
            "new_venue_city": str(self.city.pk),
            "new_venue_name": "Proposed Venue",
        }
        data.update(kw)
        return data

    def test_participant_proposes_pending_venue_used_by_competition(self):
        self.client.force_login(self.participant)
        self.client.post(reverse("calendar_submit"), self._payload())
        comp = Competition.objects.get(title_ru="Race")
        self.assertIsNotNone(comp.location)
        self.assertEqual(comp.location.name_ru, "Proposed Venue")
        self.assertTrue(comp.location.is_pending)
        self.assertEqual(comp.location.proposal.submitted_by, self.participant)
        self.assertEqual(comp.status, Competition.Status.PENDING_APPROVAL)

    def test_organizer_proposed_venue_is_approved(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse("calendar_submit"), self._payload(title_ru="OrgRace", new_venue_name="Org Venue"))
        comp = Competition.objects.get(title_ru="OrgRace")
        self.assertEqual(comp.location.name_ru, "Org Venue")
        self.assertFalse(comp.location.is_pending)

    def test_approving_competition_auto_approves_location(self):
        self.client.force_login(self.participant)
        self.client.post(reverse("calendar_submit"), self._payload(new_venue_name="Auto Venue"))
        comp = Competition.objects.get(title_ru="Race")
        self.assertTrue(comp.location.is_pending)
        comp.approve(reviewer=self.organizer)
        comp.location.refresh_from_db()
        self.assertFalse(comp.location.is_pending)

    def test_existing_venue_used_when_no_proposal(self):
        venue = self.city.add_child(name_ru="Existing", name_en="Existing")
        self.client.force_login(self.participant)
        self.client.post(
            reverse("calendar_submit"),
            {"title_ru": "Plain", "date_start": "2026-09-01", "location": str(venue.pk)},
        )
        comp = Competition.objects.get(title_ru="Plain")
        self.assertEqual(comp.location.pk, venue.pk)

    def test_forged_post_cannot_use_other_users_pending_location(self):
        other = _make_user("forger_owner@example.com", User.Role.PARTICIPANT)
        pending = Location.propose_venue(self.city, "Other Pending", submitted_by=other)
        self.client.force_login(self.participant)
        resp = self.client.post(
            reverse("calendar_submit"),
            {"title_ru": "Forge", "date_start": "2026-09-01", "location": str(pending.pk)},
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with a form error
        self.assertFalse(Competition.objects.filter(title_ru="Forge").exists())

    def test_can_use_own_pending_location(self):
        pending = Location.propose_venue(self.city, "Mine", submitted_by=self.participant)
        self.client.force_login(self.participant)
        self.client.post(
            reverse("calendar_submit"),
            {"title_ru": "MineRace", "date_start": "2026-09-01", "location": str(pending.pk)},
        )
        self.assertEqual(Competition.objects.get(title_ru="MineRace").location_id, pending.pk)

    def test_forged_post_rejects_structural_location(self):
        # A competition must point at a venue, not a city/region/country (depth 3 here).
        self.client.force_login(self.participant)
        resp = self.client.post(
            reverse("calendar_submit"),
            {"title_ru": "Struct", "date_start": "2026-09-01", "location": str(self.city.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Competition.objects.filter(title_ru="Struct").exists())

    def test_forged_post_rejects_non_city_new_venue_parent(self):
        self.client.force_login(self.participant)
        resp = self.client.post(
            reverse("calendar_submit"),
            {
                "title_ru": "BadCity",
                "date_start": "2026-09-01",
                "new_venue_city": str(self.country.pk),  # depth 1, not a city
                "new_venue_name": "X",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Competition.objects.filter(title_ru="BadCity").exists())


class SubmitCompetitionScenariosTests(TestCase):
    """Dense coverage of competition creation - a core flow with many parameters. In
    particular submitting must never 500 when a city's venue paths have drifted from sort
    order, which used to crash the propose-a-new-venue path (#118)."""

    def setUp(self):
        self.participant = _make_user("p_sub@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("o_sub@example.com", User.Role.ORGANIZER)
        self.cat = DisciplineCategory.objects.create(name_ru="Road", order=1)
        self.disc = Discipline.objects.create(name_ru="Road Race", category=self.cat, order=1)
        self.event_type = EventType.objects.create(name_ru="Race", order=1)
        self.country = Location.add_root(name_ru="KZ", name_en="KZ")
        self.region = self.country.add_child(name_ru="Region", name_en="Region")
        self.city = self.region.add_child(name_ru="City", name_en="City")
        self.venue = self.city.add_child(name_ru="Velodrome", name_en="Velodrome", lat="43.200000", lng="76.900000")
        self.url = reverse("calendar_submit")

    def _payload(self, **kw):
        data = {"title_ru": "Race", "date_start": "2026-09-01"}
        data.update(kw)
        return data

    def _desync_city(self):
        """Rename the city's first venue so its path order no longer matches sort order."""
        first = self.city.get_children().order_by("path").first()
        first.name = first.name_ru = "ZZZ Renamed"
        first.save()
        self.city.refresh_from_db()

    # --- existing-venue selection ---
    def test_organizer_existing_venue_is_approved(self):
        self.client.force_login(self.organizer)
        resp = self.client.post(self.url, self._payload(title_ru="V1", location=str(self.venue.pk)))
        self.assertEqual(resp.status_code, 302)
        comp = Competition.objects.get(title_ru="V1")
        self.assertEqual(comp.location.pk, self.venue.pk)
        self.assertEqual(comp.status, Competition.Status.APPROVED)

    def test_participant_existing_venue_is_pending(self):
        self.client.force_login(self.participant)
        self.client.post(self.url, self._payload(title_ru="V2", location=str(self.venue.pk)))
        self.assertEqual(Competition.objects.get(title_ru="V2").status, Competition.Status.PENDING_APPROVAL)

    def test_hidden_fallback_venue_is_accepted(self):
        hidden = Location.get_or_create_other_location(self.city)
        self.client.force_login(self.organizer)
        self.client.post(self.url, self._payload(title_ru="V3", location=str(hidden.pk)))
        self.assertEqual(Competition.objects.get(title_ru="V3").location.pk, hidden.pk)

    # --- propose a new venue ---
    def test_participant_proposes_pending_venue(self):
        self.client.force_login(self.participant)
        self.client.post(
            self.url, self._payload(title_ru="V4", new_venue_city=str(self.city.pk), new_venue_name="New Spot")
        )
        comp = Competition.objects.get(title_ru="V4")
        self.assertEqual(comp.location.name_ru, "New Spot")
        self.assertTrue(comp.location.is_pending)

    def test_organizer_proposes_approved_venue_with_coords(self):
        self.client.force_login(self.organizer)
        self.client.post(
            self.url,
            self._payload(
                title_ru="V5",
                new_venue_city=str(self.city.pk),
                new_venue_name="Org Spot",
                new_venue_lat="43.100000",
                new_venue_lng="76.800000",
            ),
        )
        comp = Competition.objects.get(title_ru="V5")
        self.assertFalse(comp.location.is_pending)
        self.assertEqual(str(comp.location.lat), "43.100000")

    # --- regression: a desynced city must not 500 ---
    def test_propose_new_venue_into_desynced_city_does_not_500(self):
        self._desync_city()
        self.client.force_login(self.participant)
        resp = self.client.post(
            self.url, self._payload(title_ru="V6", new_venue_city=str(self.city.pk), new_venue_name="After Rename")
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Competition.objects.filter(title_ru="V6").exists())

    def test_existing_venue_in_desynced_city_does_not_500(self):
        self._desync_city()
        self.client.force_login(self.organizer)
        resp = self.client.post(self.url, self._payload(title_ru="V7", location=str(self.venue.pk)))
        self.assertEqual(resp.status_code, 302)

    def test_propose_into_city_with_many_venues_does_not_500(self):
        for i in range(6):
            self.city.add_child(name_ru=f"v{i}", name_en=f"v{i}", sort_order=0)
        self._desync_city()
        self.client.force_login(self.organizer)
        resp = self.client.post(
            self.url, self._payload(title_ru="V8", new_venue_city=str(self.city.pk), new_venue_name="Crowded")
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Competition.objects.filter(title_ru="V8").exists())

    def test_two_successive_proposals_into_same_city(self):
        self.client.force_login(self.organizer)
        self.client.post(
            self.url, self._payload(title_ru="V9a", new_venue_city=str(self.city.pk), new_venue_name="First")
        )
        self.client.post(
            self.url, self._payload(title_ru="V9b", new_venue_city=str(self.city.pk), new_venue_name="Second")
        )
        self.assertTrue(Competition.objects.filter(title_ru="V9a").exists())
        self.assertTrue(Competition.objects.filter(title_ru="V9b").exists())

    # --- varied parameters ---
    def test_full_details_with_date_end_discipline_and_urls(self):
        self.client.force_login(self.organizer)
        resp = self.client.post(
            self.url,
            self._payload(
                title_ru="V10",
                title_en="V10en",
                date_start="2026-09-01",
                date_end="2026-09-03",
                disciplines=[str(self.disc.pk)],
                event_type=str(self.event_type.pk),
                description_ru="Some description",
                url_announcement="https://example.com/a",
                url_results="https://example.com/r",
                location=str(self.venue.pk),
            ),
        )
        self.assertEqual(resp.status_code, 302)
        comp = Competition.objects.get(title_ru="V10")
        self.assertEqual(comp.date_end, datetime.date(2026, 9, 3))
        self.assertEqual(list(comp.disciplines.values_list("pk", flat=True)), [self.disc.pk])
        self.assertEqual(comp.event_type.pk, self.event_type.pk)

    def test_multiple_disciplines_are_saved(self):
        self.client.force_login(self.organizer)
        other = Discipline.objects.create(name_ru="Gravel", category=self.cat, order=2)
        resp = self.client.post(
            self.url,
            self._payload(
                title_ru="V-multi",
                disciplines=[str(self.disc.pk), str(other.pk)],
                location=str(self.venue.pk),
            ),
        )
        self.assertEqual(resp.status_code, 302)
        comp = Competition.objects.get(title_ru="V-multi")
        self.assertEqual(set(comp.disciplines.values_list("pk", flat=True)), {self.disc.pk, other.pk})

    def test_without_date_end(self):
        self.client.force_login(self.organizer)
        self.client.post(self.url, self._payload(title_ru="V11", location=str(self.venue.pk)))
        self.assertIsNone(Competition.objects.get(title_ru="V11").date_end)

    def test_missing_title_returns_form_not_500(self):
        self.client.force_login(self.organizer)
        resp = self.client.post(self.url, self._payload(title_ru="", location=str(self.venue.pk)))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Competition.objects.filter(location=self.venue).exists())

    def test_missing_date_returns_form_not_500(self):
        self.client.force_login(self.organizer)
        resp = self.client.post(self.url, {"title_ru": "NoDate", "location": str(self.venue.pk)})
        self.assertEqual(resp.status_code, 200)

    def test_end_before_start_returns_form_not_500(self):
        self.client.force_login(self.organizer)
        resp = self.client.post(
            self.url,
            self._payload(title_ru="V12", date_start="2026-09-05", date_end="2026-09-01", location=str(self.venue.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Competition.objects.filter(title_ru="V12").exists())

    def test_new_venue_without_city_is_ignored_not_500(self):
        # A venue name with no city is silently ignored (no venue created), but must not 500.
        self.client.force_login(self.organizer)
        resp = self.client.post(self.url, self._payload(title_ru="V13", new_venue_name="Orphan"))
        self.assertIn(resp.status_code, (200, 302))
        self.assertFalse(Location.objects.filter(name_ru="Orphan").exists())


class LocationDataVisibilityTests(TestCase):
    """Pending locations are visible only to their proposer (issue #111)."""

    def setUp(self):
        self.user = _make_user("viz@example.com", User.Role.PARTICIPANT)
        self.other = _make_user("other_viz@example.com", User.Role.PARTICIPANT)
        country = Location.add_root(name_ru="KZ", name_en="KZ")
        region = country.add_child(name_ru="Region", name_en="Region")
        self.city = region.add_child(name_ru="City", name_en="City")
        self.approved = Location.propose_venue(self.city, "Approved Venue", submitted_by=self.user, approved=True)
        self.pending = Location.propose_venue(self.city, "Pending Venue", submitted_by=self.user)

    def test_approved_visible_without_user(self):
        from calendar_app.views import _get_locations_data

        pks = {loc["pk"] for loc in _get_locations_data()}
        self.assertIn(self.approved.pk, pks)
        self.assertNotIn(self.pending.pk, pks)

    def test_own_pending_visible_to_submitter(self):
        from calendar_app.views import _get_locations_data

        pks = {loc["pk"] for loc in _get_locations_data(self.user)}
        self.assertIn(self.pending.pk, pks)

    def test_pending_not_visible_to_other_user(self):
        from calendar_app.views import _get_locations_data

        pks = {loc["pk"] for loc in _get_locations_data(self.other)}
        self.assertNotIn(self.pending.pk, pks)


class ModerationPendingLocationsTests(TestCase):
    def setUp(self):
        self.admin = _make_user("modadmin@example.com", User.Role.ADMIN)
        self.organizer = _make_user("modorg@example.com", User.Role.ORGANIZER)
        country = Location.add_root(name_ru="KZ", name_en="KZ")
        region = country.add_child(name_ru="Region", name_en="Region")
        city = region.add_child(name_ru="City", name_en="City")
        self.pending = Location.propose_venue(city, "Pending Venue", submitted_by=self.organizer)

    def test_admin_sees_pending_locations(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("calendar_moderate"))
        self.assertIn("pending_locations", resp.context)
        self.assertIn(self.pending, list(resp.context["pending_locations"]))

    def test_organizer_does_not_see_pending_locations(self):
        self.client.force_login(self.organizer)
        resp = self.client.get(reverse("calendar_moderate"))
        self.assertIsNone(resp.context.get("pending_locations"))


class CompetitionRichDescriptionTests(TestCase):
    def setUp(self):
        self.organizer = _make_user("rt_org@example.com", User.Role.ORGANIZER)

    def test_vendored_quill_ships_its_license(self):
        # Quill is BSD-3-Clause; vendoring it requires shipping its license/notice.
        from pathlib import Path

        from django.contrib.staticfiles import finders

        path = finders.find("calendar_app/vendor/quill/LICENSE")
        self.assertIsNotNone(path, "vendored Quill LICENSE is missing")
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("BSD 3-Clause", text)
        self.assertIn("Quill", text)

    def test_submit_page_ships_local_quill_editor(self):
        self.client.force_login(self.organizer)
        resp = self.client.get(reverse("calendar_submit"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "vendor/quill/quill.snow.css")
        self.assertContains(resp, "vendor/quill/quill.min.js")
        self.assertNotContains(resp, "cdn.quilljs.com")  # vendored locally, not a CDN
        for loc in ("ru", "kk", "en"):
            self.assertContains(resp, f'id="quill-desc-{loc}"')
            self.assertContains(resp, f'id="init-desc-{loc}"')

    def test_edit_page_ships_local_quill_editor(self):
        comp = _make_competition(title="Editable", description_ru="<p>hi</p>", submitted_by=self.organizer)
        self.client.force_login(self.organizer)
        resp = self.client.get(reverse("competition_edit", args=[comp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "vendor/quill/quill.min.js")
        self.assertContains(resp, 'id="quill-desc-ru"')

    def test_submit_sanitizes_description(self):
        self.client.force_login(self.organizer)
        html = (
            "<p>Hi <strong>x</strong></p>"
            '<a href="https://x.com">l</a>'
            '<img src="https://x.com/i.png" alt="a">'
            "<script>alert(1)</script>"
        )
        self.client.post(
            reverse("calendar_submit"),
            {"title_ru": "RT Race", "date_start": "2026-09-01", "description_ru": html},
        )
        comp = Competition.objects.get(title_ru="RT Race")
        self.assertIn("<strong>x</strong>", comp.description_ru)
        self.assertIn('href="https://x.com"', comp.description_ru)
        self.assertIn('target="_blank"', comp.description_ru)
        self.assertIn("<img", comp.description_ru)  # images allowed for competitions
        self.assertNotIn("<script", comp.description_ru)

    def test_detail_renders_description_as_html(self):
        # Competition.save() sanitizes (which also normalises <a> attribute order).
        comp = _make_competition(
            title="RT Detail",
            description_ru='<p>see <a href="https://x.com">link</a></p>',
        )
        resp = self.client.get(reverse("competition_detail", args=[comp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '<a href="https://x.com" rel="noopener" target="_blank">link</a>')
        self.assertNotContains(resp, "&lt;p&gt;")  # rendered as HTML, not escaped

    def test_submit_rejects_oversized_description(self):
        from calendar_app.models import MAX_DESCRIPTION_LENGTH

        self.client.force_login(self.organizer)
        resp = self.client.post(
            reverse("calendar_submit"),
            {
                "title_ru": "Too Big",
                "date_start": "2026-09-01",
                "description_ru": "a" * (MAX_DESCRIPTION_LENGTH + 1),
            },
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors, not redirected
        self.assertFalse(Competition.objects.filter(title_ru="Too Big").exists())

    def test_model_save_sanitizes_description(self):
        # Sanitization is centralized in Competition.save(), so every write path -- including
        # Django admin and the Wagtail snippet, which both persist via the model -- is covered.
        comp = Competition.objects.create(
            title_ru="Model Save",
            date_start=datetime.date(2026, 9, 1),
            description_ru="<p>ok</p><script>alert(1)</script>",
            description_en='<a href="javascript:alert(1)">x</a>',
        )
        comp.refresh_from_db()
        self.assertIn("<p>ok</p>", comp.description_ru)
        self.assertNotIn("<script", comp.description_ru)
        self.assertNotIn("javascript:", comp.description_en)

    def test_save_does_not_leak_translation_across_active_locales(self):
        # Regression: save() must not copy one language's body into an empty translation
        # under a non-default active UI locale (modeltranslation canonical-fallback footgun).
        from django.utils import translation

        for active in ("ru", "kk", "en"):
            with translation.override(active):
                comp = Competition.objects.create(
                    title_ru=f"Iso {active}",
                    date_start=datetime.date(2026, 9, 1),
                    description_ru="<p>RU body</p><script>x</script>",
                )
            comp.refresh_from_db()
            self.assertIn("<p>RU body</p>", comp.description_ru)
            self.assertNotIn("<script", comp.description_ru)
            self.assertFalse(comp.description_kk, f"kk leaked under active={active}")
            self.assertFalse(comp.description_en, f"en leaked under active={active}")
            self.assertNotIn("<script", comp.__dict__.get("description") or "")

    def test_admin_save_model_sanitizes_description(self):
        from django.contrib.admin.sites import AdminSite

        from calendar_app.admin import CompetitionAdmin

        obj = Competition(
            title_ru="Admin Race",
            date_start=datetime.date(2026, 9, 1),
            description_ru="<p>fine</p><script>alert(1)</script>",
        )
        CompetitionAdmin(Competition, AdminSite()).save_model(None, obj, None, False)
        obj.refresh_from_db()
        self.assertIn("<p>fine</p>", obj.description_ru)
        self.assertNotIn("<script", obj.description_ru)

    def test_migration_converts_plaintext_descriptions(self):
        import importlib

        from django.apps import apps as django_apps

        # Plant the historical value with .update() to bypass Competition.save()'s
        # sanitizer -- the migration runs against rows written before that sanitizer
        # existed. Use a non-default locale: the canonical ``description`` is a
        # modeltranslation alias for the default language (ru) on the real model, so
        # iterating both would convert ru twice here. In a real migration the historical
        # model has independent columns, so each is converted exactly once.
        comp = _make_competition(title="Mig")
        Competition.objects.filter(pk=comp.pk).update(description_en="Plain text https://x.com line")
        mig = importlib.import_module("calendar_app.migrations.0013_descriptions_to_html")
        mig.descriptions_to_html(django_apps, None)
        comp.refresh_from_db()
        self.assertIn('href="https://x.com"', comp.description_en)
        self.assertIn("<p>", comp.description_en)

    def test_migration_escapes_html_no_passthrough(self):
        # Historical values that happen to contain HTML must be escaped, never passed
        # through raw (which would become stored XSS once rendered with |safe). Plant the
        # raw value with .update() to bypass the save()-time sanitizer (see above).
        import importlib

        from django.apps import apps as django_apps

        comp = _make_competition(title="Mig2")
        Competition.objects.filter(pk=comp.pk).update(description_en="<script>alert(1)</script>")
        mig = importlib.import_module("calendar_app.migrations.0013_descriptions_to_html")
        mig.descriptions_to_html(django_apps, None)
        comp.refresh_from_db()
        self.assertNotIn("<script>", comp.description_en)
        self.assertIn("&lt;script&gt;", comp.description_en)


class LocationsDataOrderingTests(TestCase):
    """_get_locations_data feeds the cascade filters, so hidden / coordinate-less nodes must
    come last in its output (the filters preserve this order when building options)."""

    def test_get_locations_data_orders_hidden_and_coordless_last(self):
        from calendar_app.views import _get_locations_data

        Location.add_root(name="A", name_ru="A", name_en="A", lat="43.000000", lng="76.000000")
        Location.add_root(name="Hidden", name_ru="Hidden", is_hidden=True, lat="44.0", lng="77.0")
        Location.add_root(name="NoCoords", name_ru="NoCoords", name_en="NoCoords")
        created = {"A", "NoCoords", "Hidden"}
        names = [r["name_ru"] for r in _get_locations_data() if r["name_ru"] in created]
        self.assertEqual(names, ["A", "NoCoords", "Hidden"])


class CompetitionDisciplinesMigrationTests(TransactionTestCase):
    """0014 must copy the old single discipline FK into the new disciplines M2M, and must
    refuse to reverse when collapsing several disciplines back to one would drop data."""

    APP = "calendar_app"
    BEFORE = "0013_descriptions_to_html"
    AFTER = "0014_competition_disciplines"

    def tearDown(self):
        # Restore the schema to the latest migration for the rest of the suite.
        from django.core.management import call_command

        call_command("migrate", self.APP, verbosity=0)

    def _migrate(self, target):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate([(self.APP, target)])
        return executor.loader.project_state([(self.APP, target)]).apps

    def test_forward_copies_discipline_fk_to_m2m(self):
        import datetime

        apps = self._migrate(self.BEFORE)
        cat = apps.get_model(self.APP, "DisciplineCategory").objects.create(name="Road")
        disc = apps.get_model(self.APP, "Discipline").objects.create(name="Road Race", category=cat)
        comp = apps.get_model(self.APP, "Competition").objects.create(
            title="X", date_start=datetime.date(2026, 7, 1), discipline=disc
        )
        apps = self._migrate(self.AFTER)
        migrated = apps.get_model(self.APP, "Competition").objects.get(pk=comp.pk)
        self.assertEqual(list(migrated.disciplines.values_list("pk", flat=True)), [disc.pk])

    def test_reverse_refuses_when_a_competition_has_multiple_disciplines(self):
        import datetime

        apps = self._migrate(self.AFTER)
        cat = apps.get_model(self.APP, "DisciplineCategory").objects.create(name="Road")
        d1 = apps.get_model(self.APP, "Discipline").objects.create(name="Road Race", category=cat)
        d2 = apps.get_model(self.APP, "Discipline").objects.create(name="Gravel", category=cat)
        comp = apps.get_model(self.APP, "Competition").objects.create(title="X", date_start=datetime.date(2026, 7, 1))
        comp.disciplines.set([d1, d2])
        with self.assertRaises(RuntimeError):
            self._migrate(self.BEFORE)


class OtherAndMtbDisciplineMigrationTests(TransactionTestCase):
    """0016 qualifies each generic "Other" discipline with its direction and adds the two missing
    Mountain Bike formats. Assertions use ASCII (name_en) so the test file stays non-Cyrillic."""

    APP = "calendar_app"
    BEFORE = "0015_discipline_category_required"
    AFTER = "0016_qualify_other_and_add_mtb_disciplines"

    def tearDown(self):
        from django.core.management import call_command

        call_command("migrate", self.APP, verbosity=0)

    def _migrate(self, target):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate([(self.APP, target)])
        return executor.loader.project_state([(self.APP, target)]).apps

    def test_other_discipline_gets_direction_suffix_in_every_locale(self):
        apps = self._migrate(self.BEFORE)
        cat = apps.get_model(self.APP, "DisciplineCategory").objects.create(
            name="DirRU", name_ru="DirRU", name_kk="DirKK", name_en="DirEN", order=99
        )
        d = apps.get_model(self.APP, "Discipline").objects.create(
            name="GenRU", name_ru="GenRU", name_kk="GenKK", name_en="Other", category=cat, order=99
        )
        apps = self._migrate(self.AFTER)
        migrated = apps.get_model(self.APP, "Discipline").objects.get(pk=d.pk)
        self.assertEqual(migrated.name_en, "Other (DirEN)")
        self.assertEqual(migrated.name_ru, "GenRU (DirRU)")
        self.assertEqual(migrated.name_kk, "GenKK (DirKK)")
        self.assertEqual(migrated.name, "GenRU (DirRU)")
        # No bare generic name should survive the migration.
        self.assertFalse(apps.get_model(self.APP, "Discipline").objects.filter(name_en="Other").exists())

    def test_mtb_formats_are_added_under_mountain_bike(self):
        apps = self._migrate(self.BEFORE)
        # The migration targets the seeded "Mountain Bike" category; in a full TransactionTestCase
        # run the seed data is flushed, so ensure the category exists rather than relying on it.
        apps.get_model(self.APP, "DisciplineCategory").objects.get_or_create(
            name_en="Mountain Bike", defaults={"name": "MTB", "name_ru": "MTB", "name_kk": "MTB", "order": 50}
        )
        apps = self._migrate(self.AFTER)
        Discipline = apps.get_model(self.APP, "Discipline")
        for name_en in ("Individual Time Trial (MTB)", "Hill Climb (MTB)"):
            d = Discipline.objects.filter(name_en=name_en, category__name_en="Mountain Bike").first()
            self.assertIsNotNone(d, name_en)
            self.assertTrue(d.name_ru and d.name_kk, f"{name_en} missing localized names")

    def _make_mtb_category(self, apps):
        cat, _ = apps.get_model(self.APP, "DisciplineCategory").objects.get_or_create(
            name_en="Mountain Bike", defaults={"name": "MTB", "name_ru": "MTB", "name_kk": "MTB", "order": 50}
        )
        return cat

    def test_reverse_refuses_to_drop_an_mtb_discipline_linked_to_a_competition(self):
        apps = self._migrate(self.BEFORE)
        self._make_mtb_category(apps)
        apps = self._migrate(self.AFTER)
        Discipline = apps.get_model(self.APP, "Discipline")
        Competition = apps.get_model(self.APP, "Competition")
        itt = Discipline.objects.get(name_en="Individual Time Trial (MTB)", category__name_en="Mountain Bike")
        comp = Competition.objects.create(title="Race", date_start=datetime.date(2026, 7, 1))
        comp.disciplines.add(itt)
        with self.assertRaises(RuntimeError):
            self._migrate(self.BEFORE)
        # The refused rollback left both the discipline and the competition link intact.
        self.assertTrue(Discipline.objects.filter(pk=itt.pk).exists())
        self.assertEqual(list(comp.disciplines.values_list("pk", flat=True)), [itt.pk])

    def test_reverse_leaves_disciplines_added_after_the_migration_untouched(self):
        apps = self._migrate(self.BEFORE)
        self._make_mtb_category(apps)
        apps = self._migrate(self.AFTER)
        Discipline = apps.get_model(self.APP, "Discipline")
        mtb = apps.get_model(self.APP, "DisciplineCategory").objects.get(name_en="Mountain Bike")
        # A generic-looking discipline created AFTER the migration must survive a rollback unchanged.
        custom = Discipline.objects.create(
            name="Other (Custom)",
            name_ru="Other (Custom)",
            name_kk="Other (Custom)",
            name_en="Other (Custom)",
            category=mtb,
            order=80,
        )
        apps = self._migrate(self.BEFORE)  # no linked MTB formats -> rollback is allowed
        survived = apps.get_model(self.APP, "Discipline").objects.get(pk=custom.pk)
        self.assertEqual(survived.name_en, "Other (Custom)")


class RegistrationDeadlineMigrationTests(TransactionTestCase):
    """0018 shifts legacy date-only (midnight) deadlines to end-of-day so registration stays
    open for the whole deadline day, preserving the old DateField semantics."""

    APP = "calendar_app"
    BEFORE = "0017_alter_competition_registration_deadline"
    AFTER = "0018_shift_date_deadlines_to_end_of_day"

    def tearDown(self):
        from django.core.management import call_command

        call_command("migrate", self.APP, verbosity=0)

    def _migrate(self, target):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate([(self.APP, target)])
        return executor.loader.project_state([(self.APP, target)]).apps

    def test_forward_shifts_legacy_midnight_deadline_to_end_of_day(self):
        import datetime

        # The runtime helper computes the expected value, cross-checking the migration's own
        # (deliberately self-contained) copy of the same transform.
        from calendar_app.registration_deadline import date_only_to_end_of_day

        apps = self._migrate(self.BEFORE)
        midnight_utc = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
        comp = apps.get_model(self.APP, "Competition").objects.create(
            title="X", date_start=datetime.date(2026, 9, 1), registration_deadline=midnight_utc
        )
        apps = self._migrate(self.AFTER)
        migrated = apps.get_model(self.APP, "Competition").objects.get(pk=comp.pk)
        self.assertEqual(migrated.registration_deadline, date_only_to_end_of_day(midnight_utc))

    def test_forward_leaves_real_time_deadline_untouched(self):
        import datetime

        apps = self._migrate(self.BEFORE)
        dt = datetime.datetime(2026, 9, 1, 14, 30, tzinfo=datetime.UTC)
        comp = apps.get_model(self.APP, "Competition").objects.create(
            title="Y", date_start=datetime.date(2026, 9, 1), registration_deadline=dt
        )
        apps = self._migrate(self.AFTER)
        migrated = apps.get_model(self.APP, "Competition").objects.get(pk=comp.pk)
        self.assertEqual(migrated.registration_deadline, dt)
