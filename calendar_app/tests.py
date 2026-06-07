import datetime
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition, CyclingDiscipline, EventType


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
        self.assertIn("disciplines", response.context)
        self.assertIn("locations_data", response.context)


class CalendarEventsAPIViewTests(TestCase):
    def setUp(self):
        self.event_type = EventType.objects.create(name_ru="Race")
        self.discipline = CyclingDiscipline.objects.create(name_ru="Road")
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
        self.comp = _make_competition(status=Competition.Status.APPROVED)
        self.pending = _make_competition("Pending", status=Competition.Status.PENDING_APPROVAL)

    def test_detail_returns_200_for_approved(self):
        response = self.client.get(reverse("competition_detail", args=[self.comp.pk]))
        self.assertEqual(response.status_code, 200)

    def test_detail_returns_404_for_pending(self):
        response = self.client.get(reverse("competition_detail", args=[self.pending.pk]))
        self.assertEqual(response.status_code, 404)


class SubmitCompetitionViewTests(TestCase):
    def setUp(self):
        self.participant = _make_user("participant@example.com", User.Role.PARTICIPANT)
        self.organizer = _make_user("organizer@example.com", User.Role.ORGANIZER)
        self.guest = _make_user("guest@example.com", User.Role.GUEST)

    def _submit_url(self):
        return reverse("calendar_submit")

    def _payload(self, **kwargs):
        data = {
            "title": "My Race",
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
        self.client.post(self._submit_url(), self._payload(title="Organizer Race"))
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
