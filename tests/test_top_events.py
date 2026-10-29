"""Top events: an admin's mark that puts an event first wherever events are listed."""

import datetime
import uuid
from typing import ClassVar

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition
from locations.models import Location


def _user(name, role):
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return user


def _venue():
    country = Location.add_root(name_ru="KZ", name_en="KZ")
    city = country.add_child(name_ru="Region", name_en="Region").add_child(name_ru="City", name_en="City")
    return city.add_child(name_ru="Venue", name_en="Venue", lat=43.2, lng=76.9)


class TopEventMarkTests(TestCase):
    """Who may set the mark, on the site and through the API."""

    def setUp(self):
        self.admin = _user("admin", User.Role.ADMIN)
        self.organizer = _user("org", User.Role.ORGANIZER)
        self.venue = _venue()

    def _payload(self, **extra):
        return {"title_ru": "Race", "date_start": "2026-11-20", "location": str(self.venue.pk), **extra}

    def test_only_an_admin_is_offered_the_mark(self):
        self.client.force_login(self.organizer)
        self.assertNotContains(self.client.get(reverse("calendar_submit")), 'name="is_top"')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("calendar_submit")), 'name="is_top"')

    def test_an_organizer_posting_the_mark_does_not_get_it(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse("calendar_submit"), self._payload(is_top="on"))
        self.assertFalse(Competition.objects.get(title_ru="Race").is_top)

    def test_an_admin_marks_and_unmarks(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("calendar_submit"), self._payload(is_top="on"))
        comp = Competition.objects.get(title_ru="Race")
        self.assertTrue(comp.is_top)
        self.client.post(reverse("competition_edit", args=[comp.pk]), self._payload())
        comp.refresh_from_db()
        self.assertFalse(comp.is_top)

    def test_the_author_editing_a_top_event_leaves_the_mark(self):
        comp = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 11, 20),
            submitted_by=self.organizer,
            location=self.venue,
            status=Competition.Status.APPROVED,
            is_top=True,
        )
        self.client.force_login(self.organizer)
        self.client.post(reverse("competition_edit", args=[comp.pk]), self._payload(title_ru="Race 2"))
        comp.refresh_from_db()
        self.assertEqual(comp.title_ru, "Race 2")
        self.assertTrue(comp.is_top)

    def test_a_clone_starts_without_the_mark(self):
        comp = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 11, 20),
            submitted_by=self.admin,
            location=self.venue,
            status=Competition.Status.APPROVED,
            is_top=True,
        )
        self.client.force_login(self.admin)
        edit = self.client.get(reverse("competition_edit", args=[comp.pk]))
        self.assertTrue(edit.context["form"]["is_top"].value())
        clone = self.client.get(reverse("calendar_submit") + f"?clone={comp.pk}")
        self.assertFalse(clone.context["form"]["is_top"].value())

    def test_the_api_shows_the_mark_and_lets_admins_alone_change_it(self):
        comp = Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date(2026, 11, 20),
            submitted_by=self.organizer,
            location=self.venue,
            status=Competition.Status.APPROVED,
        )
        url = f"/api/v1/competitions/{comp.pk}"
        self.assertIs(self.client.get(url).json()["is_top"], False)
        organizer = {"HTTP_AUTHORIZATION": f"Bearer {self.organizer.api_token}"}
        admin = {"HTTP_AUTHORIZATION": f"Bearer {self.admin.api_token}"}
        response = self.client.patch(url, {"is_top": True}, content_type="application/json", **organizer)
        self.assertEqual(response.status_code, 403)
        response = self.client.patch(url, {"is_top": True}, content_type="application/json", **admin)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["is_top"], True)
        created = {"title": {"ru": "New"}, "date_start": "2026-11-21", "location_id": self.venue.pk, "is_top": True}
        response = self.client.post("/api/v1/competitions/", created, content_type="application/json", **organizer)
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/v1/competitions/", created, content_type="application/json", **admin)
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()["is_top"], True)


class TopEventOrderTests(TestCase):
    """A top event goes first wherever events are listed."""

    window: ClassVar[dict] = {"date_from": "2027-03-01", "date_to": "2027-03-31"}

    def setUp(self):
        self.venue = _venue()
        approved = {"status": Competition.Status.APPROVED, "location": self.venue}
        self.early = Competition.objects.create(title_ru="Early", date_start=datetime.date(2027, 3, 2), **approved)
        self.top = Competition.objects.create(
            title_ru="Top",
            date_start=datetime.date(2027, 3, 20),
            date_end=datetime.date(2027, 3, 21),
            is_top=True,
            **approved,
        )
        self.late = Competition.objects.create(title_ru="Late", date_start=datetime.date(2027, 3, 25), **approved)

    def test_the_list_puts_top_events_first_above_a_divider(self):
        response = self.client.get("/en/calendar/list/", self.window)
        self.assertEqual([c.title for c in response.context["competitions"]], ["Top", "Early", "Late"])
        self.assertContains(response, '<tbody class="calendar-list-rest">', count=1)
        days = response.context["days"]
        self.assertEqual(days[0]["label"], "Top events")
        self.assertEqual([row["comp"].title for row in days[0]["rows"]], ["Top"])
        self.assertEqual(days[0]["rows"][0]["when"], "20 March \u2013 21 March")
        self.assertEqual([day["rows"][0]["comp"].title for day in days[1:]], ["Early", "Late"])

    def test_a_page_of_top_events_alone_draws_no_divider(self):
        Competition.objects.exclude(pk=self.top.pk).update(is_top=True)
        self.assertNotContains(self.client.get("/en/calendar/list/", self.window), '<tbody class="calendar-list-rest">')

    def test_the_calendar_is_told_which_event_is_top(self):
        events = self.client.get(reverse("calendar_events_api"), {"start": "2027-03-01", "end": "2027-04-01"}).json()
        self.assertEqual(
            {e["title"]: e["extendedProps"]["top"] for e in events}, {"Early": False, "Top": True, "Late": False}
        )

    def test_the_map_lists_a_top_event_first_at_its_place(self):
        places = self.client.get(reverse("calendar_map_api"), self.window).json()
        self.assertEqual([c["title"] for c in places[0]["competitions"]], ["Top", "Early", "Late"])

    def test_the_nearest_events_start_with_the_top_ones(self):
        from django.contrib.auth.models import AnonymousUser

        from calendar_app.views import upcoming_competitions

        today = timezone.localdate()
        Competition.objects.all().delete()
        approved = {"status": Competition.Status.APPROVED, "location": self.venue}
        Competition.objects.create(title_ru="Soon", date_start=today + datetime.timedelta(days=2), **approved)
        Competition.objects.create(
            title_ru="Top later", date_start=today + datetime.timedelta(days=10), is_top=True, **approved
        )
        self.assertEqual([c.title for c in upcoming_competitions(AnonymousUser())], ["Top later", "Soon"])
