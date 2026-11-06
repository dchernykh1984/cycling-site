"""What the participants think of an event (issue #436): the figures and the language model's digest, for the
people who edit the event alone, from two reviews up, written again only once more reviews came."""

import json
from http import HTTPStatus
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from assistant import llm
from ratings import form
from ratings.models import Review, ReviewSummary
from registrations.tests import make_competition, make_user
from tests.test_virtual_members import _bearer


def _url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs)


def _reviewed(competition, *answers):
    for score, comment in answers:
        Review.objects.create(
            competition=competition, form=form.VERSION, answers={form.RATED: score, "comment": comment}
        )


class DigestTests(TestCase):
    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER, first_name="Pavel", last_name="Melnikov")
        self.event = make_competition(title="Duathlon", submitted_by=self.organizer)
        self.page = _url("ratings:summary", pk=self.event.pk)

    def _model(self, summary="- The course was clear\n- The start was late"):
        return mock.patch("assistant.llm.complete", return_value={"summary": summary})

    def test_only_the_people_who_edit_the_event_see_what_its_participants_think(self):
        _reviewed(self.event, (4, "Good"), (5, "Great"))
        self.client.force_login(make_user("stranger"))
        self.assertEqual(self.client.get(self.page).status_code, HTTPStatus.NOT_FOUND)
        for person in (self.organizer, make_user("admin", role=User.Role.ADMIN)):
            self.client.force_login(person)
            self.assertEqual(self.client.get(self.page).status_code, HTTPStatus.OK)
        self.assertContains(self.client.get(self.event.get_absolute_url()), self.page)

    def test_nothing_but_the_count_shows_before_two_reviews(self):
        _reviewed(self.event, (1, "Bad"))
        self.client.force_login(self.organizer)
        page = self.client.get(self.page)
        self.assertContains(page, "Reviews: 1")
        self.assertNotContains(page, "Average score")
        with self._model() as model:
            self.client.post(self.page)
        model.assert_not_called()
        self.assertFalse(ReviewSummary.objects.exists())

    def test_the_model_is_told_the_scores_and_the_words_and_nothing_of_who_wrote_them(self):
        _reviewed(self.event, (4, "Clear course"), (2, "Late start"))
        self.client.force_login(self.organizer)
        with self._model() as model:
            self.client.post(self.page)
        sent = json.loads(model.call_args.args[0][1]["content"])
        self.assertEqual(
            sorted(sent["reviews"], key=lambda r: r["score"]),
            [
                {"score": 2, "comment": "Late start"},
                {"score": 4, "comment": "Clear course"},
            ],
        )
        page = self.client.get(self.page)
        self.assertContains(page, "The course was clear")
        self.assertContains(page, "<strong>3.0</strong>", html=True)
        self.assertContains(page, "Written from reviews: 2.")
        self.assertNotContains(page, "Write the digest")  # nothing new to write it from

    def test_a_digest_is_written_again_only_once_more_reviews_came(self):
        _reviewed(self.event, (4, "A"), (5, "B"))
        self.client.force_login(self.organizer)
        with self._model():
            self.client.post(self.page)
        _reviewed(self.event, (3, "C"))
        self.assertContains(self.client.get(self.page), "Write the digest again")
        with self._model("- Updated") as model:
            self.client.post(self.page)
        self.assertEqual(len(json.loads(model.call_args.args[0][1]["content"])["reviews"]), 3)
        self.assertEqual(ReviewSummary.objects.get().reviews, 3)

    def test_with_nothing_new_to_write_it_from_the_model_is_not_asked_again(self):
        _reviewed(self.event, (4, "A"), (5, "B"))
        self.client.force_login(self.organizer)
        with self._model():
            self.client.post(self.page)
        api = f"/api/v1/ratings/events/{self.event.pk}/summary?language=en"
        with self._model("- Again") as model:
            self.client.post(self.page)
            again = self.client.post(api, **_bearer(self.organizer)).json()
        model.assert_not_called()
        self.assertEqual(again["digest"], "- The course was clear\n- The start was late")
        self.assertEqual(ReviewSummary.objects.get().reviews, 2)

    def test_when_the_model_does_not_answer_the_page_says_so_and_keeps_nothing(self):
        _reviewed(self.event, (4, "A"), (5, "B"))
        self.client.force_login(self.organizer)
        failing = mock.patch("assistant.llm.complete", side_effect=llm.UnavailableError(llm.UnavailableError.BUSY))
        with failing:
            page = self.client.post(self.page, follow=True)
        self.assertContains(page, "the language model did not answer")
        self.assertFalse(ReviewSummary.objects.exists())

    def test_through_the_api_as_on_the_page(self):
        _reviewed(self.event, (4, "A"), (5, "B"))
        url = f"/api/v1/ratings/events/{self.event.pk}/summary?language=en"
        stranger = _bearer(make_user("stranger"))
        self.assertEqual(self.client.get(url, **stranger).status_code, HTTPStatus.FORBIDDEN)
        auth = _bearer(self.organizer)
        before = self.client.get(url, **auth).json()
        self.assertEqual((before["reviews"], before["average"], before["digest"]), (2, 4.5, None))
        self.assertEqual(before["spread"], {"5": 1, "4": 1, "3": 0, "2": 0, "1": 0})
        with self._model("- Fine"):
            written = self.client.post(url, **auth).json()
        self.assertEqual((written["digest"], written["digest_reviews"]), ("- Fine", 2))
        Review.objects.filter(competition=self.event).first().delete()
        self.assertEqual(self.client.post(url, **auth).status_code, HTTPStatus.CONFLICT)


class OwnDigestsTests(TestCase):
    """Under the organizers' ratings, the reader's own events with reviews enough for a digest: what the
    participants think is found without remembering every event one posted. Only one's own, whatever the
    role: an admin edits every event, and a list of all of them would bury their own."""

    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER)
        self.ready = make_competition(title="Duathlon", submitted_by=self.organizer)
        _reviewed(self.ready, (4, "A"), (5, "B"))
        self.single = make_competition(title="Night run", submitted_by=self.organizer)
        _reviewed(self.single, (3, "C"))
        other = make_user("other", role=User.Role.ORGANIZER)
        _reviewed(make_competition(title="Somebody else's race", submitted_by=other), (5, "D"), (5, "E"))
        self.page = _url("ratings:index")

    def test_an_organizer_finds_under_the_ratings_their_events_with_reviews_enough_for_a_digest(self):
        self.client.force_login(self.organizer)
        page = self.client.get(self.page).content.decode()
        self.assertIn(_url("ratings:summary", pk=self.ready.pk), page)
        self.assertNotIn(_url("ratings:summary", pk=self.single.pk), page)  # one review: nothing to sum up
        self.assertNotIn("Somebody else", page)
        self.assertLess(page.index("organizer-ratings"), page.index("own-digests"))  # under the ratings

    def test_admins_and_owners_get_only_their_own_events_there_and_nobody_else_any(self):
        for role in (User.Role.ADMIN, User.Role.OWNER, User.Role.PARTICIPANT):
            with self.subTest(role):
                self.client.force_login(make_user(f"m-{role}", role=role))
                self.assertNotContains(self.client.get(self.page), "own-digests")
        self.client.logout()
        self.assertNotContains(self.client.get(self.page), "own-digests")

    def test_each_says_whether_its_digest_is_still_to_be_written(self):
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(self.page), "No digest yet")
        with mock.patch("assistant.llm.complete", return_value={"summary": "- Fine"}):
            self.client.post(_url("ratings:summary", pk=self.ready.pk))
        page = self.client.get(self.page)
        self.assertNotContains(page, "No digest yet")
        self.assertNotContains(page, "New reviews since the digest")
        _reviewed(self.ready, (2, "F"))
        self.assertContains(self.client.get(self.page), "New reviews since the digest")

    def test_through_the_api_as_on_the_page(self):
        rows = self.client.get("/api/v1/ratings/mine?language=en", **_bearer(self.organizer)).json()
        self.assertEqual(
            [(row["competition_id"], row["reviews"], row["digest_reviews"]) for row in rows], [(self.ready.pk, 2, None)]
        )
        self.assertEqual(self.client.get("/api/v1/ratings/mine", **_bearer(make_user("rider"))).json(), [])
