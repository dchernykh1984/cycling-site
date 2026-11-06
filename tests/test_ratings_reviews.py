"""Reviews of an event by the members who took part in it (issue #436): who is asked and when, what a
review keeps -- nothing of its author -- and that rating or refusing is the one answer."""

import datetime
from http import HTTPStatus

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import User
from audit.models import AuditLog
from event_photos.models import IssuedBib
from protocols.models import Protocol
from ratings import rules
from ratings.models import Review, ReviewMark
from registrations.tests import make_competition, make_registration, make_user
from tests.test_virtual_members import _bearer

# The events below have no place, so their days are counted in UTC
TODAY = datetime.datetime.now(datetime.UTC).date()


def _url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs)


def _protocol(competition, rows, document=True):
    """A protocol the timing programs sent: the data with a bib column, or the HTML alone."""
    columns = [{"id": "bib", "label": "Bib", "role": "bib"}, {"id": "name", "label": "Name", "role": "name"}]
    data = {"schema": 1, "sections": [{"type": "table", "columns": columns, "rows": rows}]} if document else None
    return Protocol.objects.create(competition=competition, protocol_type="absolute", document=data)


def _row(bib, status=None):
    row = {"cells": {"bib": bib, "name": "A rider"}}
    if status:
        row["status"] = status
    return row


LOCAL_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ratings-tests"}}


class ReviewTests(TestCase):
    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER, first_name="Pavel", last_name="Org")
        self.rider = make_user("rider", first_name="Dana", last_name="Kim")
        self.event = self._event(TODAY - datetime.timedelta(days=1))
        self.entry = self._enter(self.event, self.rider, "7")
        _protocol(self.event, [_row("7"), _row("8", "dns"), _row("9", "dnf")])

    def _event(self, day, organizer=None):
        return make_competition(title="Autumn Cup", date_start=day, submitted_by=organizer or self.organizer)

    def _enter(self, event, user, bib, **kwargs):
        entry = make_registration(event, user=user, **kwargs)
        IssuedBib.objects.create(competition=event, registration=entry, bib=bib)
        return entry

    def test_a_member_the_protocol_lists_is_asked_from_the_day_after_the_last_day(self):
        self.client.force_login(self.rider)
        self.assertContains(self.client.get(_url("news_index")), "review-requests")
        self.assertEqual(rules.reviewable(self.rider), [self.event])
        today = self._event(TODAY)
        self._enter(today, self.rider, "7")
        _protocol(today, [_row("7")])
        self.assertEqual(rules.reviewable(self.rider), [self.event])  # not on the day itself

    def test_nobody_is_asked_who_did_not_start_or_is_its_organizer_or_whose_event_the_agents_posted(self):
        cases = {
            "did not start": ("8", {}),
            "did not finish, but started": ("9", {}),
            "entry rejected": ("7", {"is_rejected": True}),
        }
        for name, (bib, extra) in cases.items():
            with self.subTest(name):
                member = make_user(f"m{bib}{len(extra)}")
                self._enter(self.event, member, bib, **extra)
                expected = [self.event] if name == "did not finish, but started" else []
                self.assertEqual(rules.reviewable(member), expected)
        self.assertEqual(rules.reviewable(self._entered_in_own_event()), [])
        agent = make_user("agent", is_service_account=True)
        agents_event = self._event(TODAY - datetime.timedelta(days=2), organizer=agent)
        self._enter(agents_event, self.rider, "3")
        _protocol(agents_event, [_row("3")])
        html_only = self._event(TODAY - datetime.timedelta(days=3))
        self._enter(html_only, self.rider, "5")
        _protocol(html_only, [], document=False)
        disputed = self._event(TODAY - datetime.timedelta(days=4))
        entry = self._enter(disputed, self.rider, "6")
        IssuedBib.objects.filter(registration=entry).update(state=IssuedBib.State.CONFLICT)
        _protocol(disputed, [_row("6")])
        self.assertEqual(rules.reviewable(self.rider), [self.event])

    def _entered_in_own_event(self):
        self._enter(self.event, self.organizer, "11")
        Protocol.objects.filter(competition=self.event).update(
            document={"sections": [{"columns": [{"id": "bib", "role": "bib"}], "rows": [_row("7"), _row("11")]}]}
        )
        return self.organizer

    def test_a_review_keeps_neither_its_author_nor_its_time_and_ends_the_asking(self):
        audited = AuditLog.objects.count()
        self.client.force_login(self.rider)
        sent = self.client.post(_url("ratings:review", pk=self.event.pk), {"overall": "4", "comment": "Clear course"})
        self.assertEqual(sent.status_code, HTTPStatus.FOUND)
        review = Review.objects.get()
        self.assertEqual({field.name for field in Review._meta.fields}, {"id", "competition", "form", "answers"})
        self.assertEqual(review.answers, {"overall": 4, "comment": "Clear course"})
        self.assertEqual(ReviewMark.objects.get().user, self.rider)
        self.assertEqual({field.name for field in ReviewMark._meta.fields}, {"id", "user", "competition"})
        self.assertEqual(AuditLog.objects.count(), audited)
        self.assertNotContains(self.client.get(_url("news_index")), "review-requests")
        self.client.post(_url("ratings:review", pk=self.event.pk), {"overall": "1"})
        self.assertEqual(Review.objects.count(), 1)

    def test_refusing_is_as_final_as_a_review_and_leaves_the_same_mark(self):
        self.client.force_login(self.rider)
        self.client.post(_url("ratings:review", pk=self.event.pk), {"decline": "1"})
        self.assertTrue(ReviewMark.objects.filter(user=self.rider, competition=self.event).exists())
        self.assertFalse(Review.objects.exists())
        self.assertEqual(rules.reviewable(self.rider), [])
        self.client.post(_url("ratings:review", pk=self.event.pk), {"overall": "5"})
        self.assertFalse(Review.objects.exists())
        self.assertEqual(self.client.get(_url("ratings:review", pk=self.event.pk)).status_code, HTTPStatus.NOT_FOUND)

    def test_the_score_is_required_from_one_to_five_and_the_comment_may_be_left_out(self):
        self.client.force_login(self.rider)
        for sent in ({"overall": "7"}, {"comment": "No score"}):
            with self.subTest(sent):
                page = self.client.post(_url("ratings:review", pk=self.event.pk), sent)
                self.assertContains(page, "Choose a score from 1 to 5.")
        self.client.post(_url("ratings:review", pk=self.event.pk), {"overall": "5", "comment": "  "})
        self.assertEqual(Review.objects.get().answers, {"overall": 5})

    @override_settings(CACHES=LOCAL_CACHE)
    def test_the_banner_reads_the_protocols_once_until_one_of_them_changes(self):
        cache.clear()
        rules.reviewable(self.rider)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(rules.reviewable(self.rider), [self.event])
        read = [
            q["sql"] for q in queries.captured_queries if q["sql"].startswith('SELECT "protocols_protocol"."document"')
        ]
        self.assertEqual(read, [])
        Protocol.objects.filter(competition=self.event).update(
            document={"sections": [{"columns": [{"id": "bib", "role": "bib"}], "rows": [_row("7", "dns")]}]},
            last_updated=timezone.now() + datetime.timedelta(seconds=5),
        )
        self.assertEqual(rules.reviewable(self.rider), [])

    def test_through_the_api_as_on_the_page(self):
        auth = _bearer(self.rider)
        pending = self.client.get("/api/v1/ratings/pending", **auth).json()
        self.assertEqual([row["competition_id"] for row in pending], [self.event.pk])
        url = f"/api/v1/ratings/events/{self.event.pk}/review"
        wrong = self.client.post(url, {"answers": {"overall": 0}}, content_type="application/json", **auth)
        self.assertEqual(wrong.status_code, HTTPStatus.UNPROCESSABLE_ENTITY)
        sent = self.client.post(
            url, {"answers": {"overall": 3, "comment": "Fine"}}, content_type="application/json", **auth
        )
        self.assertEqual(sent.status_code, HTTPStatus.NO_CONTENT)
        again = self.client.post(url, {"answers": {"overall": 3}}, content_type="application/json", **auth)
        self.assertEqual(again.status_code, HTTPStatus.CONFLICT)
        other = _bearer(make_user("stranger"))
        refused = self.client.post(f"/api/v1/ratings/events/{self.event.pk}/decline", **other)
        self.assertEqual(refused.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(Review.objects.count(), 1)
