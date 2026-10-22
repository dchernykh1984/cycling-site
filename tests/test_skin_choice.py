"""Which skin a page is drawn in (cycling_site/skins.py): the member's profile, the guest's cookie,
the site default for anything else -- and the two attributes on <html> always agree."""

import re

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from cycling_site.skins import COOKIE


def _attributes(response):
    html = response.content.decode()
    tag = re.search(r"<html[^>]*>", html).group(0)
    return re.search(r'data-skin="([^"]*)"', tag).group(1), re.search(r'data-bs-theme="([^"]*)"', tag).group(1)


# The skin under test is set here, not taken from DEFAULT_SKIN, which is free to change.
@override_settings(DEFAULT_SKIN="light")
class ChosenSkinTests(TestCase):
    page = "/ru/privacy/"

    def _member(self, theme):
        member = User.objects.create_user(username="m", email="m@example.com", password="pw", theme=theme)
        self.client.force_login(member)
        return member

    def test_a_member_sees_the_skin_in_their_profile(self):
        self._member("dark")
        self.assertEqual(_attributes(self.client.get(self.page)), ("dark", "dark"))

    def test_a_member_whose_skin_is_gone_sees_the_default_and_keeps_the_choice(self):
        member = self._member("retired-skin")
        self.assertEqual(_attributes(self.client.get(self.page)), ("light", "light"))
        member.refresh_from_db()
        self.assertEqual(member.theme, "retired-skin")

    def test_a_guest_sees_the_skin_in_their_cookie(self):
        self.client.cookies[COOKIE] = "dark"
        self.assertEqual(_attributes(self.client.get(self.page)), ("dark", "dark"))

    def test_a_guest_with_an_unknown_cookie_sees_the_default(self):
        self.client.cookies[COOKIE] = "retired-skin"
        self.assertEqual(_attributes(self.client.get(self.page)), ("light", "light"))

    def test_a_first_visit_sees_the_default(self):
        self.assertEqual(_attributes(self.client.get(self.page)), ("light", "light"))

    @override_settings(DEFAULT_SKIN="dark")
    def test_the_default_is_a_setting(self):
        self.assertEqual(_attributes(self.client.get(self.page)), ("dark", "dark"))
        self.assertEqual(User.objects.create_user(username="n", email="n@example.com", password="pw").theme, "dark")

    def test_only_a_guest_without_the_cookie_gets_the_script_that_carries_an_old_choice_over(self):
        self.assertContains(self.client.get(self.page), "localStorage.getItem('theme')")
        self.client.cookies[COOKIE] = "dark"
        self.assertNotContains(self.client.get(self.page), "localStorage.getItem('theme')")


# The skin under test is set here, not taken from DEFAULT_SKIN, which is free to change.
@override_settings(DEFAULT_SKIN="light")
class SaveChoiceTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="m", email="m@example.com", password="pw")
        self.client.force_login(self.member)

    def _post(self, theme):
        return self.client.post(reverse("account_theme"), data={"theme": theme}, content_type="application/json")

    def test_any_skin_in_the_folder_is_accepted(self):
        self.assertEqual(self._post("dark").status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.theme, "dark")

    def test_a_malformed_request_is_refused_not_crashed_on(self):
        for body in ('{"theme": ["dark"]}', '["dark"]', "{}"):
            with self.subTest(body=body):
                response = self.client.post(reverse("account_theme"), data=body, content_type="application/json")
                self.assertEqual(response.status_code, 400)

    def test_an_unknown_skin_is_refused(self):
        self.assertEqual(self._post("retired-skin").status_code, 400)
        self.member.refresh_from_db()
        self.assertEqual(self.member.theme, "light")
