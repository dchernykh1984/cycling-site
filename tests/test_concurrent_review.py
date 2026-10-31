"""Two moderators acting on one event at once: the one who acted first wins, the other is refused."""

import datetime
from unittest import mock

from django.test import TestCase

from accounts.models import User
from calendar_app.models import Competition, CompetitionRejection
from locations.models import Location


class ConcurrentReviewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", "a@example.com", "pw", role=User.Role.ADMIN)
        region = Location.add_root(name_ru="Testland", name_en="Testland").add_child(name_ru="R", name_en="R")
        venue = region.add_child(name_ru="Testville", name_en="Testville").add_child(name_ru="Shop", name_en="Shop")
        self.event = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 11, 20),
            location=venue,
            status=Competition.Status.PENDING_APPROVAL,
        )

    def _seen_earlier(self) -> Competition:
        """The event as a moderator's page loaded it, before somebody else acted on it."""
        return Competition.objects.get(pk=self.event.pk)

    def test_approving_what_was_rejected_meanwhile_is_refused(self):
        stale = self._seen_earlier()
        self._seen_earlier().reject(reviewer=self.admin, reason="A duplicate")
        with self.assertRaises(ValueError):
            stale.approve(reviewer=self.admin)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Competition.Status.REJECTED)

    def test_rejecting_what_was_approved_meanwhile_is_refused(self):
        stale = self._seen_earlier()
        self._seen_earlier().approve(reviewer=self.admin)
        with self.assertRaises(ValueError):
            stale.reject(reviewer=self.admin, reason="Too late")
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Competition.Status.APPROVED)
        self.assertFalse(CompetitionRejection.objects.filter(competition=self.event).exists())

    def test_the_approve_page_goes_back_when_the_event_was_handled_meanwhile(self):
        self.client.force_login(self.admin)
        refused = ValueError("Cannot approve: competition is already 'Rejected'.")
        with mock.patch.object(Competition, "approve", side_effect=refused):
            answer = self.client.post(f"/en/calendar/{self.event.pk}/approve/")
        self.assertEqual(answer.status_code, 302)
