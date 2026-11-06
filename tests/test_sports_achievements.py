"""The profile's sports achievements: a rank or category, or the like, in the member's own words. The
profile keeps and shows them; no registration form takes them (the maintainer, 2026-11-06)."""

from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from accounts.models import User
from registrations.forms import RegistrationForm
from registrations.tests import make_open_competition, make_user


class SportsAchievementsTests(TestCase):
    def setUp(self):
        self.member = make_user("rider", first_name="Ivan", last_name="Petrov")
        self.client.force_login(self.member)

    def _url(self, name):
        with translation.override("ru"):
            return reverse(name)

    def test_the_edit_page_asks_for_them_with_the_hint_under_the_field(self):
        page = self.client.get(self._url("account_profile_edit"))
        with translation.override("ru"):
            label, hint = gettext("Sports achievements"), gettext("A sports rank or category, or the like")
        self.assertContains(page, f'<label class="form-label" for="id_sports_achievements">{label}</label>', html=True)
        self.assertContains(page, f'<div class="form-text" id="sports-achievements-hint">{hint}</div>', html=True)
        self.assertContains(page, 'aria-describedby="sports-achievements-hint"')

    def test_the_profile_keeps_and_shows_them(self):
        data = {"first_name": "Ivan", "last_name": "Petrov", "sports_achievements": "  KMS in road cycling "}
        self.client.post(self._url("account_profile_edit"), data)
        self.member.refresh_from_db()
        self.assertEqual(self.member.sports_achievements, "KMS in road cycling")
        self.assertContains(self.client.get(self._url("account_profile")), "KMS in road cycling")

    def test_too_long_is_refused_and_nothing_else_changes(self):
        data = {"first_name": "Oleg", "last_name": "Petrov", "sports_achievements": "a" * 201}
        page = self.client.post(self._url("account_profile_edit"), data)
        self.assertIn("sports_achievements", page.context["form"].errors)
        self.assertEqual(User.objects.get(pk=self.member.pk).first_name, "Ivan")

    def test_no_registration_form_takes_them(self):
        self.assertNotIn("sports_achievements", RegistrationForm(competition=make_open_competition()).fields)
