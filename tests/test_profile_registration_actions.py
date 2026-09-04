"""Edit and Cancel on the profile's own registrations.

The profile listed the reader's entries with no way to act on them: to change a name or cancel a
place they had to open the event, then the participant list, then find their own row. The two
buttons are the same ones that row carries, and they appear on the same rule -- the one the edit
and delete views themselves apply, so the profile never offers a button the server refuses.
"""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition
from registrations.models import CompetitionRegistration


def _make_user(username, role=User.Role.PARTICIPANT):
    return User.objects.create_user(username=username, email=f"{username}@example.com", password="Pass1234!", role=role)


class ProfileRegistrationActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rider = _make_user("rider")
        cls.url = reverse("account_profile")

    def _competition(self, **kwargs):
        defaults = {
            "title_ru": "Race",
            "date_start": datetime.date.today() + datetime.timedelta(days=30),
            "status": Competition.Status.APPROVED,
            "registration_enabled": True,
            "registration_mode": Competition.RegistrationMode.FREE,
            "birth_date_mode": "year",
        }
        defaults.update(kwargs)
        return Competition.objects.create(**defaults)

    def _registration(self, competition, user=None, **kwargs):
        defaults = {
            "competition": competition,
            "user": self.rider if user is None else user,
            "first_name": "Denis",
            "last_name": "Test",
            "birth_date": datetime.date(1990, 1, 1),
            "gender": "M",
        }
        defaults.update(kwargs)
        return CompetitionRegistration.objects.create(**defaults)

    def _profile(self, user=None):
        self.client.force_login(user or self.rider)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def _row(self, response, reg):
        return next(r for r in response.context["registrations"] if r.pk == reg.pk)

    def test_an_open_registration_offers_edit_and_cancel(self):
        comp = self._competition()
        reg = self._registration(comp)
        response = self._profile()
        self.assertTrue(self._row(response, reg).can_edit)
        self.assertContains(response, reverse("registrations:edit_registration", args=[comp.pk, reg.pk]))
        self.assertContains(response, reverse("registrations:delete_registration", args=[comp.pk, reg.pk]))

    def test_edit_leads_to_the_same_page_the_participant_list_leads_to(self):
        comp = self._competition()
        reg = self._registration(comp)
        self._profile()
        target = reverse("registrations:edit_registration", args=[comp.pk, reg.pk])
        self.assertEqual(self.client.get(target).status_code, 200)

    def test_a_closed_registration_offers_nothing(self):
        """Past the deadline the edit view refuses, so the profile must not show the button."""
        comp = self._competition(registration_deadline=timezone.now() - datetime.timedelta(days=1))
        reg = self._registration(comp)
        response = self._profile()
        self.assertFalse(self._row(response, reg).can_edit)
        self.assertNotContains(response, reverse("registrations:edit_registration", args=[comp.pk, reg.pk]))

    def test_registration_switched_off_offers_nothing(self):
        comp = self._competition(registration_enabled=False)
        reg = self._registration(comp)
        self.assertFalse(self._row(self._profile(), reg).can_edit)

    def test_a_rejected_entry_offers_nothing(self):
        comp = self._competition()
        reg = self._registration(comp, is_rejected=True)
        self.assertFalse(self._row(self._profile(), reg).can_edit)

    def test_a_full_field_still_lets_its_riders_edit(self):
        """The rider already holds a place, so the limit must not lock them out (ignore_limit)."""
        comp = self._competition(max_participants=1)
        reg = self._registration(comp)
        self.assertTrue(comp.is_limit_reached())
        self.assertTrue(self._row(self._profile(), reg).can_edit)

    def test_a_manager_keeps_the_buttons_after_the_deadline(self):
        """Manager rights take precedence in the edit view; the profile follows the same order."""
        organizer = _make_user("organizer", role=User.Role.ORGANIZER)
        comp = self._competition(
            submitted_by=organizer,
            registration_deadline=timezone.now() - datetime.timedelta(days=1),
        )
        reg = self._registration(comp, user=organizer)
        self.assertTrue(self._row(self._profile(organizer), reg).can_edit)

    def test_the_row_keeps_its_shape_when_nobody_may_touch_it(self):
        """The column header still stands, so the cells below it stay under the right heading."""
        import re

        from django.utils import translation

        comp = self._competition(registration_enabled=False)
        reg = self._registration(comp)
        response = self._profile()
        html = response.content.decode()
        table = re.search(r"<table[^>]*>.*?</table>", html, flags=re.S).group(0)
        headers = re.findall(r"<th[^>]*>(.*?)</th>", table, flags=re.S)
        with translation.override("ru"):
            self.assertIn(translation.gettext("Actions"), [h.strip() for h in headers])
        self.assertEqual(len(re.findall(r"<td", table.split("</thead>")[1])), len(headers))
        self.assertNotContains(response, reverse("registrations:edit_registration", args=[comp.pk, reg.pk]))
