"""A skin's own templates (skins/<key>/templates/) replace the site's for whoever chose the skin."""

import pathlib
import tempfile

from django.test import TestCase

from accounts.models import User
from cycling_site.skins import COOKIE
from tests.skin_fixtures import trial_skin

MARKER = "trial-skin-share-button"
OWN_BUTTON = {"_share_button.html": f'<span class="{MARKER}"></span>'}


class SkinTemplateTests(TestCase):
    page = "/ru/news/"

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def test_the_skin_s_template_replaces_the_site_s_for_a_member_who_chose_it(self):
        member = User.objects.create_user(username="m", email="m@example.com", password="pw", theme="trial")
        self.client.force_login(member)
        with trial_skin(self.root, templates=OWN_BUTTON):
            self.assertContains(self.client.get(self.page), MARKER)
            # The same template, cached for the skin, never reaches anyone in another skin.
            member.theme = "light"
            member.save(update_fields=["theme"])
            response = self.client.get(self.page)
            self.assertNotContains(response, MARKER)
            self.assertContains(response, "share-btn")

    def test_and_for_a_guest_whose_cookie_names_it(self):
        with trial_skin(self.root, templates=OWN_BUTTON):
            self.client.cookies[COOKIE] = "trial"
            self.assertContains(self.client.get(self.page), MARKER)

    def test_a_template_the_skin_does_not_have_is_the_site_s(self):
        with trial_skin(self.root, templates=OWN_BUTTON):
            self.client.cookies[COOKIE] = "trial"
            self.assertContains(self.client.get(self.page), 'class="navbar')

    def test_a_skin_s_stylesheet_and_script_are_on_its_pages_only(self):
        with trial_skin(self.root, script="window.trial = true;"):
            self.assertNotContains(self.client.get(self.page), "skins/trial/")
            self.client.cookies[COOKIE] = "trial"
            html = self.client.get(self.page).content.decode()
            self.assertIn("skins/trial/skin.css", html)
            self.assertIn("skins/trial/skin.js", html)
