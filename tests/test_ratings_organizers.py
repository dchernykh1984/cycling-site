"""Organizers' ratings (issue #436): the average overall score their events' participants gave, shown from
three scores on the Ratings tab, beside each of their events and through the API."""

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from ratings import form, scores
from ratings.models import Review
from registrations.tests import make_competition, make_user


def _url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs)


def _reviewed(competition, *values):
    for value in values:
        Review.objects.create(competition=competition, form=form.VERSION, answers={form.RATED: value})


class OrganizerRatingTests(TestCase):
    def setUp(self):
        self.pavel = make_user("pavel", role=User.Role.ORGANIZER, first_name="Pavel", last_name="Melnikov")
        self.anna = make_user("anna", role=User.Role.ORGANIZER, first_name="Anna", last_name="Ivanova")
        self.agent = make_user("agent", is_service_account=True, first_name="Events", last_name="Agent")
        self.duathlon = make_competition(title="Duathlon", submitted_by=self.pavel)
        _reviewed(self.duathlon, 5, 4)
        _reviewed(make_competition(title="Birthday ride", submitted_by=self.pavel), 3)
        self.anna_event = make_competition(title="Night run", submitted_by=self.anna)
        _reviewed(self.anna_event, 5, 5)  # two: not shown yet
        _reviewed(make_competition(title="Found by the agents", submitted_by=self.agent), 5, 5, 5, 5)
        hidden = make_competition(title="Hidden", submitted_by=self.anna, is_hidden=True)
        _reviewed(hidden, 5, 5, 5)  # a hidden event's scores do not count

    def test_an_organizer_is_rated_from_three_scores_over_all_their_events(self):
        self.assertEqual(
            [(row["organizer"], row["average"], row["reviews"], row["events"]) for row in scores.organizers()],
            [(self.pavel, 4.0, 3, 2)],
        )
        self.assertIsNone(scores.of_organizer(self.anna))
        self.assertIsNone(scores.of_organizer(self.agent))

    def test_the_best_rated_comes_first(self):
        _reviewed(self.anna_event, 5)
        self.assertEqual([row["organizer"] for row in scores.organizers()], [self.anna, self.pavel])

    def test_the_ratings_tab_and_an_event_page_show_the_rating(self):
        page = self.client.get(_url("ratings:index")).content.decode()
        self.assertIn("Pavel Melnikov", page)
        self.assertIn("4.0", page)
        self.assertNotIn("Anna Ivanova", page)
        self.assertNotIn("Events Agent", page)
        with translation.override("en"):
            shown = self.client.get(self.duathlon.get_absolute_url().replace("/ru/", "/en/", 1))
        self.assertContains(shown, "Organizer's rating")
        self.assertContains(shown, "3 scores")
        unrated = self.client.get(self.anna_event.get_absolute_url())
        self.assertNotContains(unrated, "organizer-rating")

    def test_the_api_gives_the_same_list(self):
        listed = self.client.get("/api/v1/ratings/organizers").json()
        self.assertEqual(
            listed, [{"user_id": self.pavel.pk, "name": "Pavel Melnikov", "average": 4.0, "reviews": 3, "events": 2}]
        )
