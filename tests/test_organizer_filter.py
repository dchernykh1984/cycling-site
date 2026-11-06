"""The calendar narrowed to organizers (issue #336): the members who posted its events, named last name
first, on the list, the grid, the map, the feed and the API -- and on the list every one of their events,
past and to come, which is where a name on the Ratings tab leads."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import User
from calendar_app import organizers
from calendar_app.models import Competition
from locations.models import Location
from ratings import form
from ratings.models import Review
from registrations.tests import make_competition, make_user
from tests.test_virtual_members import _bearer

TODAY = timezone.localdate()


def _url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs)


class OrganizerFilterTests(TestCase):
    def setUp(self):
        self.pavel = make_user("pavel", role=User.Role.ORGANIZER, first_name="Pavel", last_name="Melnikov")
        self.anna = make_user("anna", role=User.Role.ORGANIZER, first_name="Anna", last_name="Ivanova")
        country = Location.add_root(name_ru="Testland", name_en="Testland")
        city = country.add_child(name_ru="Region", name_en="Region").add_child(
            name_ru="Testville", name_en="Testville", lat=43.24, lng=76.89
        )
        venue = city.add_child(name_ru="Shop", name_en="Shop", lat=43.2389, lng=76.9453)
        self.past = make_competition(
            title="Last year's race", submitted_by=self.pavel, date_start=TODAY - datetime.timedelta(days=400)
        )
        self.coming = make_competition(
            title="Next year's race",
            submitted_by=self.pavel,
            date_start=TODAY + datetime.timedelta(days=200),
            date_end=TODAY + datetime.timedelta(days=201),
            location=venue,
        )
        self.annas = make_competition(
            title="Anna's ride", submitted_by=self.anna, date_start=TODAY + datetime.timedelta(days=3), location=venue
        )
        agent = make_user("agent", is_service_account=True, first_name="Events", last_name="Agent")
        make_competition(title="Found by the agents", submitted_by=agent, date_start=TODAY)
        newbie = make_user("newbie", first_name="New", last_name="Comer")
        make_competition(title="Waiting", submitted_by=newbie, status=Competition.Status.PENDING_APPROVAL)

    def test_the_filter_offers_whoever_posted_a_public_event_last_name_first_and_not_the_agents(self):
        self.assertEqual(
            organizers.choices(),
            [{"pk": self.anna.pk, "name": "Ivanova Anna"}, {"pk": self.pavel.pk, "name": "Melnikov Pavel"}],
        )
        page = self.client.get(_url("calendar_list")).content.decode()
        self.assertIn('id="og-btn-1"', page)
        self.assertIn("Melnikov Pavel", page)

    def test_the_list_shows_every_event_of_an_organizer_past_and_to_come(self):
        page = self.client.get(_url("calendar_list"), {"organizer": self.pavel.pk})
        self.assertEqual({c.title for c in page.context["competitions"]}, {"Last year's race", "Next year's race"})
        self.assertEqual(
            (page.context["date_from"], page.context["date_to"]), (self.past.date_start, self.coming.date_end)
        )

    def test_a_period_asked_for_wins_over_all_of_them(self):
        page = self.client.get(_url("calendar_list"), {"organizer": self.pavel.pk, "period": "upcoming"})
        self.assertEqual([c.title for c in page.context["competitions"]], ["Next year's race"])

    def test_the_grid_the_map_the_feed_and_the_api_narrow_to_them_too(self):
        start, end = TODAY.isoformat(), (TODAY + datetime.timedelta(days=400)).isoformat()
        grid = self.client.get(_url("calendar_events_api"), {"organizer": self.anna.pk, "start": start, "end": end})
        self.assertEqual([row["title"] for row in grid.json()], ["Anna's ride"])
        markers = self.client.get(
            _url("calendar_map_api"), {"organizer": self.pavel.pk, "date_from": start, "date_to": end}
        ).json()
        self.assertEqual(
            [c["title"] for marker in markers for c in marker["competitions"]],
            ["Next year's race"],
        )
        feed = self.client.get(_url("calendar_ics"), {"organizer": self.anna.pk}).content.decode()
        self.assertIn("Anna's ride", feed)
        self.assertNotIn("Next year's race", feed)
        listed = self.client.get("/api/v1/competitions/", {"organizer_ids": self.anna.pk}).json()
        self.assertEqual([row["id"] for row in listed], [self.annas.pk])
        offered = self.client.get("/api/v1/competitions/organizers").json()
        self.assertEqual([row["name"] for row in offered], ["Ivanova Anna", "Melnikov Pavel"])

    def test_the_map_page_opens_on_every_day_of_the_chosen_organizers_events(self):
        page = self.client.get(_url("calendar_map"), {"organizer": self.pavel.pk})
        self.assertEqual(
            (page.context["date_from"], page.context["date_to"]), (self.past.date_start, self.coming.date_end)
        )

    def test_an_organizers_name_on_the_ratings_tab_opens_their_events(self):
        for event in (self.past, self.coming):
            for score in (4, 5):
                Review.objects.create(competition=event, form=form.VERSION, answers={form.RATED: score})
        page = self.client.get(_url("ratings:index"))
        self.assertContains(page, f'href="{_url("calendar_list")}?organizer={self.pavel.pk}"')

    def test_an_invited_event_shows_only_to_whoever_may_see_it(self):
        Competition.objects.filter(pk=self.annas.pk).update(invite_only=True)
        self.assertNotIn({"pk": self.anna.pk, "name": "Ivanova Anna"}, organizers.choices())
        listed = self.client.get("/api/v1/competitions/", {"organizer_ids": self.anna.pk}, **_bearer(self.pavel))
        self.assertEqual(listed.json(), [])
