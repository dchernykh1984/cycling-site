"""Edit and Cancel on the profile's own registrations.

The profile listed the reader's entries with no way to act on them: to change a name or cancel a
place they had to open the event, then the participant list, then find their own row. The two
buttons are the same ones that row carries, and they appear on the same rule -- the one the edit
and delete views themselves apply, so the profile never offers a button the server refuses.
"""

import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

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


class ActiveRegistrationsSectionTests(TestCase):
    """The cards above the table: the entries a rider can still act on, nearest race first."""

    @classmethod
    def setUpTestData(cls):
        cls.rider = _make_user("card_rider")
        cls.url = reverse("account_profile")

    def _race(self, days_ahead, **kwargs):
        return Competition.objects.create(
            title_ru=f"Race in {days_ahead}",
            date_start=datetime.date.today() + datetime.timedelta(days=days_ahead),
            status=Competition.Status.APPROVED,
            registration_enabled=True,
            registration_mode=Competition.RegistrationMode.FREE,
            birth_date_mode="year",
            **kwargs,
        )

    def _entry(self, competition, user=None):
        return CompetitionRegistration.objects.create(
            competition=competition,
            user=user or self.rider,
            first_name="Denis",
            last_name="Test",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
        )

    def _profile(self, user=None):
        self.client.force_login(user or self.rider)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def test_an_open_entry_gets_a_card_with_both_buttons(self):
        comp = self._race(20)
        reg = self._entry(comp)
        response = self._profile()
        self.assertEqual([r.pk for r in response.context["active_registrations"]], [reg.pk])
        self.assertContains(response, reverse("registrations:edit_registration", args=[comp.pk, reg.pk]))
        self.assertContains(response, reverse("registrations:delete_registration", args=[comp.pk, reg.pk]))

    def test_the_card_carries_the_date_of_the_race(self):
        comp = self._race(20)
        self._entry(comp)
        self.assertContains(self._profile(), comp.date_start.strftime("%d.%m.%Y"))

    def test_the_nearest_race_comes_first(self):
        far = self._entry(self._race(60))
        near = self._entry(self._race(3))
        response = self._profile()
        self.assertEqual([r.pk for r in response.context["active_registrations"]], [near.pk, far.pk])

    def test_a_ridden_race_leaves_the_section(self):
        """Registration closes the day after the race, so its entry is history, not a card."""
        comp = self._race(-1)
        self._entry(comp)
        self.assertEqual(list(self._profile().context["active_registrations"]), [])

    def test_a_closed_deadline_leaves_the_section(self):
        comp = self._race(20, registration_deadline=timezone.now() - datetime.timedelta(hours=1))
        self._entry(comp)
        self.assertEqual(list(self._profile().context["active_registrations"]), [])

    def test_a_manager_does_not_collect_cards_for_races_already_ridden(self):
        """Manager rights outlive the window; the section is about what is still ahead."""
        organizer = _make_user("card_organizer", role=User.Role.ORGANIZER)
        old = self._race(-30, submitted_by=organizer)
        self._entry(old, user=organizer)
        soon = self._race(10, submitted_by=organizer)
        current = self._entry(soon, user=organizer)
        response = self._profile(organizer)
        self.assertEqual([r.pk for r in response.context["active_registrations"]], [current.pk])

    def test_no_section_when_nothing_is_open(self):
        with translation.override("ru"):
            heading = translation.gettext("Active registrations")
        self._entry(self._race(-5))
        self.assertNotContains(self._profile(), heading)

    def test_the_entry_still_shows_in_the_table_below(self):
        comp = self._race(-5)
        reg = self._entry(comp)
        response = self._profile()
        self.assertIn(reg.pk, [r.pk for r in response.context["registrations"]])


class ProfileRegistrationQueryCountTests(TestCase):
    """Deciding who may edit must not cost a query per row.

    An organizer's rights depend on who submitted the event, so the check touches
    ``competition.submitted_by``; without that row travelling with the registrations query the
    profile fetched it once per registration.
    """

    def _organizer_with(self, count, username):
        organizer = _make_user(username, role=User.Role.ORGANIZER)
        for n in range(count):
            comp = Competition.objects.create(
                title_ru=f"Race {n}",
                date_start=datetime.date.today() + datetime.timedelta(days=30 + n),
                status=Competition.Status.APPROVED,
                registration_enabled=True,
                registration_mode=Competition.RegistrationMode.FREE,
                birth_date_mode="year",
                submitted_by=organizer,
            )
            CompetitionRegistration.objects.create(
                competition=comp,
                user=organizer,
                first_name="Denis",
                last_name="Test",
                birth_date=datetime.date(1990, 1, 1),
                gender="M",
            )
        return organizer

    def _queries_for(self, user):
        self.client.force_login(user)
        self.client.get(reverse("account_profile"))  # warm any per-session queries
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("account_profile"))
        self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries), list(response.context["registrations"])

    def test_the_query_count_does_not_grow_with_the_number_of_registrations(self):
        few, rows_few = self._queries_for(self._organizer_with(1, "organizer_one"))
        many, rows_many = self._queries_for(self._organizer_with(6, "organizer_six"))
        self.assertEqual(len(rows_few), 1)
        self.assertEqual(len(rows_many), 6)
        self.assertTrue(all(row.can_edit for row in rows_many))
        self.assertEqual(few, many, "the profile queries once per registration")
