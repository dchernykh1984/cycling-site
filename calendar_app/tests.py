import datetime
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition, CompetitionComment, Discipline, DisciplineCategory, EventType


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
    return Competition.objects.create(**defaults)


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
            discipline=self.discipline,
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

    def test_guest_gets_403(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(self._submit_url(), self._payload())
        self.assertEqual(response.status_code, 403)

    def test_invalid_date_range_shows_error(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(
            self._submit_url(),
            self._payload(date_start="2026-09-05", date_end="2026-09-01"),
            HTTP_ACCEPT_LANGUAGE="en",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], None, "End date cannot be before start date.")

    def test_get_shows_form(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(self._submit_url())
        self.assertEqual(response.status_code, 200)


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
            discipline=self.road_disc,
        )
        self.mtb_comp = _make_competition(
            "MTB Race Event",
            status=Competition.Status.APPROVED,
            date_start=datetime.date(2026, 9, 1),
            discipline=self.mtb_disc,
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

    def test_discipline_filter_takes_priority_over_direction(self):
        """When both discipline and direction params are present, discipline wins."""
        response = self.client.get(
            reverse("calendar_events_api"),
            {"direction": self.road_cat.pk, "discipline": self.mtb_disc.pk},
        )
        data = json.loads(response.content)
        titles = [e["title"] for e in data]
        self.assertNotIn("Road Race Event", titles)
        self.assertIn("MTB Race Event", titles)

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
        self.assertIn("discipline_categories", response.context)
        self.assertIn("disciplines_json", response.context)
        cat_pks = [c.pk for c in response.context["discipline_categories"]]
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
        comp.registration_deadline = datetime.date(2020, 1, 1)
        self.assertFalse(comp.is_registration_open())

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

    def test_guest_role_gets_403(self):
        _make_user("guest@example.com", User.Role.GUEST)
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(self.add_url, {"body": "Hi"})
        self.assertEqual(response.status_code, 403)

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

    def test_delete_nonexistent_comment_returns_404(self):
        delete_url = reverse("competition_delete_comment", args=[99999])
        self.client.login(username=self.organizer.email, password="password123")
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 404)

    def test_comments_shown_on_detail_page(self):
        self._make_comment(body="Visible comment")
        response = self.client.get(reverse("competition_detail", args=[self.comp.pk]))
        self.assertContains(response, "Visible comment")
