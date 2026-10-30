"""Who approved an event, at the foot of its page and in the API, for admins (#741).

The moderation page always kept its reviewer, but the status field of the Wagtail admin and an
admin's event posted through the API kept nobody, so nobody could tell who had published an event.
Every door into APPROVED now records it; an approval from before stays unattributed rather than
being credited to whoever edits the event next.
"""

import datetime
import uuid

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from audit import middleware
from calendar_app.models import Competition


def _user(username, role, **kwargs):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="Pass1234!", role=role, **kwargs
    )
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return user


def _event(**kwargs):
    return Competition.objects.create(title_ru="Race", date_start=datetime.date(2027, 5, 1), **kwargs)


def _as_request_user(test, user):
    """What the audit middleware does for a request: the signed-in user, for the length of it."""
    middleware._thread_locals.user = user
    test.addCleanup(setattr, middleware._thread_locals, "user", None)


class ApprovalRecordTests(TestCase):
    def setUp(self):
        self.admin = _user("boss", User.Role.ADMIN, first_name="Anna", last_name="Admin")
        self.organizer = _user("org", User.Role.ORGANIZER)
        self.participant = _user("rider", User.Role.PARTICIPANT)

    def _page(self, event, viewer):
        self.client.logout()
        if viewer is not None:
            self.client.force_login(viewer)
        return self.client.get(event.get_absolute_url()).content.decode()

    def test_the_moderator_who_approved_is_named_to_admins(self):
        event = _event(status=Competition.Status.PENDING_APPROVAL)
        self.client.force_login(self.admin)
        self.client.post(reverse("competition_approve", args=[event.pk]))
        event.refresh_from_db()
        self.assertEqual(event.approved_by, self.admin)
        page = self._page(event, self.admin)
        self.assertIn('id="approval-record"', page)
        self.assertIn("Anna Admin (boss@example.com)", page)

    def test_nobody_but_an_admin_sees_it(self):
        event = _event(status=Competition.Status.PENDING_APPROVAL)
        event.approve(self.admin)
        for viewer in (None, self.participant, self.organizer):
            with self.subTest(viewer=getattr(viewer, "username", "guest")):
                self.assertNotIn('id="approval-record"', self._page(event, viewer))

    def test_a_status_set_by_hand_in_the_admin_records_who_set_it(self):
        event = _event(status=Competition.Status.PENDING_APPROVAL)
        _as_request_user(self, self.admin)
        event.status = Competition.Status.APPROVED
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.approved_by, self.admin)
        self.assertIsNotNone(event.approved_at)

    def test_an_event_rejected_and_then_approved_by_hand_names_who_approved_it(self):
        rejecter = _user("strict", User.Role.ADMIN)
        event = _event(status=Competition.Status.PENDING_APPROVAL)
        event.reject(rejecter, "No route yet")
        rejected_at = event.approved_at
        _as_request_user(self, self.admin)
        event.status = Competition.Status.APPROVED
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.approved_by, self.admin)
        self.assertGreater(event.approved_at, rejected_at)

    def test_an_old_approval_is_not_credited_to_whoever_edits_the_event_now(self):
        event = _event(status=Competition.Status.APPROVED)
        Competition.objects.filter(pk=event.pk).update(approved_by=None, approved_at=None)
        event.refresh_from_db()
        _as_request_user(self, self.admin)
        event.title_ru = "Race, renamed"
        event.save()
        event.refresh_from_db()
        self.assertIsNone(event.approved_by)
        self.assertIsNone(event.approved_at)
        self.assertNotIn('id="approval-record"', self._page(event, self.admin))

    def test_an_admins_event_from_the_api_names_the_admin(self):
        response = self.client.post(
            "/api/v1/competitions/",
            {
                "title": {"ru": "Race", "kk": "", "en": ""},
                "description": {"ru": "", "kk": "", "en": ""},
                "date_start": "2027-05-01",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin.api_token}",
        )
        self.assertEqual(response.status_code, 201)
        event = Competition.objects.get(pk=response.json()["id"])
        self.assertEqual(event.approved_by, self.admin)
        self.assertIsNotNone(event.approved_at)
        self.assertEqual(response.json()["approved_by_id"], self.admin.pk)

    def test_the_api_tells_admins_only(self):
        event = _event(status=Competition.Status.PENDING_APPROVAL)
        event.approve(self.admin)
        url = f"/api/v1/competitions/{event.pk}"
        seen = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {self.admin.api_token}").json()
        self.assertEqual(seen["approved_by_id"], self.admin.pk)
        self.assertIsNotNone(seen["approved_at"])
        for viewer in (self.organizer, self.participant):
            with self.subTest(viewer=viewer.username):
                body = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {viewer.api_token}").json()
                self.assertIsNone(body["approved_by_id"])
                self.assertIsNone(body["approved_at"])
        anonymous = self.client.get(url).json()
        self.assertIsNone(anonymous["approved_by_id"])
