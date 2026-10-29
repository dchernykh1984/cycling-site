"""Top events: an admin's mark that puts an event first wherever events are listed."""

import datetime
import uuid

from django.test import TestCase
from django.urls import reverse

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
    return city.add_child(name_ru="Venue", name_en="Venue")


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
