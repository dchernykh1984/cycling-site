"""An event's way through review, at the foot of its page and in the API, for admins (#741).

The moderation page always kept its reviewer, but the status field of the Wagtail admin and an
admin's event posted through the API kept nobody, and a rejection, a resubmission and an approval
before it left no trace of their order, so nobody could tell who had done what to an event. Every
move to another status is now a step -- who, when, and a rejection's reason -- whatever door it took;
an old event's steps come from what was recorded then, and nothing is credited to whoever edits it
next.
"""

import datetime
import importlib
import uuid

from django.apps import apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit import middleware
from calendar_app.models import Competition, CompetitionRejection, CompetitionStatusChange
from tests.language_urls import in_language

Status = Competition.Status


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


def _steps(event):
    return [
        (step.added, step.status, step.previous_status, step.changed_by_id, step.reason)
        for step in event.status_changes.all()
    ]


class ModerationHistoryTests(TestCase):
    def setUp(self):
        self.admin = _user("boss", User.Role.ADMIN, first_name="Anna", last_name="Admin")
        self.organizer = _user("org", User.Role.ORGANIZER)
        self.participant = _user("rider", User.Role.PARTICIPANT)

    def _page(self, event, viewer, language="en"):
        self.client.logout()
        if viewer is not None:
            self.client.force_login(viewer)
        return self.client.get(in_language(event.get_absolute_url(), language)).content.decode()

    def _post_as_api(self, user, url, payload):
        return self.client.post(
            url, payload, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {user.api_token}"
        )

    def test_a_rejection_a_resubmission_and_an_approval_are_steps_in_order(self):
        response = self._post_as_api(
            self.organizer,
            "/api/v1/competitions/",
            {
                "title": {"ru": "Race", "kk": "", "en": ""},
                "description": {"ru": "", "kk": "", "en": ""},
                "date_start": "2027-05-01",
            },
        )
        event = Competition.objects.get(pk=response.json()["id"])
        self.client.force_login(self.admin)
        self.client.post(reverse("competition_reject", args=[event.pk]), {"rejection_reason": "No route yet"})
        self.client.force_login(self.organizer)
        self.client.post(reverse("competition_resubmit", args=[event.pk]))
        self.client.force_login(self.admin)
        self.client.post(reverse("competition_approve", args=[event.pk]))
        event.refresh_from_db()
        self.assertEqual(event.status, Status.APPROVED)
        self.assertEqual(
            _steps(event),
            [
                (True, Status.PENDING_APPROVAL, "", self.organizer.pk, ""),
                (False, Status.REJECTED, Status.PENDING_APPROVAL, self.admin.pk, "No route yet"),
                (False, Status.PENDING_APPROVAL, Status.REJECTED, self.organizer.pk, ""),
                (False, Status.APPROVED, Status.PENDING_APPROVAL, self.admin.pk, ""),
            ],
        )
        page = self._page(event, self.admin)
        history = page[page.index('id="moderation-history"') :]
        shown = [
            history.index(text)
            for text in ("Added for review", "Rejected", "No route yet", "Resubmitted for review", "Approved")
        ]
        self.assertEqual(shown, sorted(shown))
        self.assertIn("Anna Admin (boss@example.com)", history)
        self.assertIn("org@example.com", history)

    def test_admins_and_those_above_them_see_it_and_nobody_else(self):
        owner = _user("chief", User.Role.OWNER)
        event = _event(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        for viewer in (self.admin, owner):
            with self.subTest(viewer=viewer.username):
                self.assertIn('id="moderation-history"', self._page(event, viewer))
                body = self.client.get(
                    f"/api/v1/competitions/{event.pk}", HTTP_AUTHORIZATION=f"Bearer {viewer.api_token}"
                ).json()
                self.assertEqual(len(body["moderation_history"]), 2)
        for viewer in (None, self.participant, self.organizer):
            with self.subTest(viewer=getattr(viewer, "username", "guest")):
                self.assertNotIn('id="moderation-history"', self._page(event, viewer))

    def test_it_speaks_the_language_of_the_page(self):
        from django.utils import translation

        event = _event(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        with translation.override("ru"):
            approved = translation.gettext("Approved")
            title = translation.gettext("Moderation history")
        self.assertNotEqual(approved, "Approved")
        page = self._page(event, self.admin, language="ru")
        self.assertIn(title, page)
        self.assertIn(approved, page[page.index('id="moderation-history"') :])

    def test_a_status_set_by_hand_in_the_admin_records_who_set_it(self):
        event = _event(status=Status.PENDING_APPROVAL)
        _as_request_user(self, self.admin)
        event.status = Status.APPROVED
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.approved_by, self.admin)
        self.assertIsNotNone(event.approved_at)
        self.assertEqual(_steps(event)[-1], (False, Status.APPROVED, Status.PENDING_APPROVAL, self.admin.pk, ""))

    def test_an_approved_event_sent_back_for_review_says_so(self):
        event = _event(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        _as_request_user(self, self.organizer)
        event.status = Status.PENDING_APPROVAL
        event.save()
        last = event.status_changes.last()
        self.assertEqual((last.previous_status, last.changed_by), (Status.APPROVED, self.organizer))
        from django.utils import translation

        with translation.override("en"):
            self.assertEqual(last.label, "Returned for review")

    def test_an_event_rejected_and_then_approved_by_hand_names_who_approved_it(self):
        rejecter = _user("strict", User.Role.ADMIN)
        event = _event(status=Status.PENDING_APPROVAL)
        event.reject(rejecter, "No route yet")
        rejected_at = event.approved_at
        _as_request_user(self, self.admin)
        event.status = Status.APPROVED
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.approved_by, self.admin)
        self.assertGreater(event.approved_at, rejected_at)
        self.assertEqual(
            [(step.status, step.changed_by_id) for step in event.status_changes.filter(added=False)],
            [(Status.REJECTED, rejecter.pk), (Status.APPROVED, self.admin.pk)],
        )

    def test_a_save_that_leaves_the_status_unwritten_records_no_step(self):
        event = _event(status=Status.PENDING_APPROVAL)
        _as_request_user(self, self.admin)
        event.status = Status.APPROVED
        event.title_ru = "Race, renamed"
        event.save(update_fields=["title_ru"])
        event.refresh_from_db()
        self.assertEqual(event.status, Status.PENDING_APPROVAL)
        self.assertIsNone(event.approved_by)
        self.assertIsNone(event.approved_at)
        self.assertEqual(event.status_changes.count(), 1)

    def test_an_edit_that_keeps_the_status_adds_no_step(self):
        event = _event(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        _as_request_user(self, self.organizer)
        event.title_ru = "Race, renamed"
        event.save()
        self.assertEqual(event.status_changes.count(), 2)

    def test_an_old_approval_is_not_credited_to_whoever_edits_the_event_now(self):
        event = _event(status=Status.APPROVED)
        Competition.objects.filter(pk=event.pk).update(approved_by=None, approved_at=None)
        event.refresh_from_db()
        _as_request_user(self, self.admin)
        event.title_ru = "Race, renamed"
        event.save()
        event.refresh_from_db()
        self.assertIsNone(event.approved_by)
        self.assertIsNone(event.approved_at)
        self.assertFalse(event.status_changes.filter(changed_by=self.admin).exists())

    def test_an_admins_event_from_the_api_names_the_admin(self):
        response = self._post_as_api(
            self.admin,
            "/api/v1/competitions/",
            {
                "title": {"ru": "Race", "kk": "", "en": ""},
                "description": {"ru": "", "kk": "", "en": ""},
                "date_start": "2027-05-01",
            },
        )
        self.assertEqual(response.status_code, 201)
        event = Competition.objects.get(pk=response.json()["id"])
        self.assertEqual(event.approved_by, self.admin)
        self.assertIsNotNone(event.approved_at)
        self.assertEqual(response.json()["approved_by_id"], self.admin.pk)
        self.assertEqual(_steps(event), [(True, Status.APPROVED, "", self.admin.pk, "")])

    def test_the_api_tells_admins_only(self):
        event = _event(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        url = f"/api/v1/competitions/{event.pk}"
        seen = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {self.admin.api_token}").json()
        self.assertEqual(seen["approved_by_id"], self.admin.pk)
        self.assertIsNotNone(seen["approved_at"])
        self.assertEqual(
            [(step["added"], step["status"], step["changed_by_id"]) for step in seen["moderation_history"]],
            [(True, Status.PENDING_APPROVAL, None), (False, Status.APPROVED, self.admin.pk)],
        )
        for viewer in (self.organizer, self.participant):
            with self.subTest(viewer=viewer.username):
                body = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {viewer.api_token}").json()
                self.assertIsNone(body["approved_by_id"])
                self.assertIsNone(body["approved_at"])
                self.assertIsNone(body["moderation_history"])
        anonymous = self.client.get(url).json()
        self.assertIsNone(anonymous["approved_by_id"])
        self.assertIsNone(anonymous["moderation_history"])


class BackfillTests(TestCase):
    """The steps of the events that were there before the history was kept."""

    def setUp(self):
        self.admin = _user("boss", User.Role.ADMIN)
        self.organizer = _user("org", User.Role.ORGANIZER)
        self.backfill = importlib.import_module("calendar_app.migrations.0038_competitionstatuschange").backfill

    def _old(self, **kwargs):
        # Saved the way an event was saved then: the audit log notes its creation, and no step is kept.
        _as_request_user(self, self.organizer)
        event = _event(submitted_by=self.organizer, **kwargs)
        middleware._thread_locals.user = None
        return event

    def test_old_events_get_the_steps_that_were_recorded_and_no_others(self):
        approved = self._old(status=Status.PENDING_APPROVAL)
        approved.reject(self.admin, "No route yet")
        approved.resubmit()
        approved.approve(self.admin)
        rejected_before_the_history = self._old(status=Status.PENDING_APPROVAL)
        rejected_before_the_history.reject(self.admin, "Past event")
        CompetitionRejection.objects.filter(competition=rejected_before_the_history).delete()
        pending = self._old(status=Status.PENDING_APPROVAL)
        CompetitionStatusChange.objects.all().delete()

        self.backfill(apps, None)

        self.assertEqual(
            _steps(approved),
            [
                (True, "", "", self.organizer.pk, ""),
                (False, Status.REJECTED, "", self.admin.pk, "No route yet"),
                (False, Status.APPROVED, "", self.admin.pk, ""),
            ],
        )
        self.assertEqual(
            _steps(rejected_before_the_history),
            [(True, "", "", self.organizer.pk, ""), (False, Status.REJECTED, "", self.admin.pk, "Past event")],
        )
        self.assertEqual(_steps(pending), [(True, "", "", self.organizer.pk, "")])
        approved.refresh_from_db()
        self.assertEqual(approved.status_changes.last().changed_at, approved.approved_at)

    def test_an_event_that_already_has_steps_is_left_alone(self):
        event = _event(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        before = _steps(event)
        self.backfill(apps, None)
        self.assertEqual(_steps(event), before)

    def test_an_event_with_no_creation_entry_starts_where_its_record_does(self):
        event = self._old(status=Status.PENDING_APPROVAL)
        event.approve(self.admin)
        CompetitionStatusChange.objects.all().delete()
        apps.get_model("audit", "AuditLog").objects.filter(object_id=str(event.pk), action="created").delete()
        self.backfill(apps, None)
        self.assertEqual(_steps(event), [(False, Status.APPROVED, "", self.admin.pk, "")])
        self.assertLess(event.status_changes.get().changed_at, timezone.now())
