"""A skin's own templates (skins/<key>/templates/) replace the site's for whoever chose the skin."""

import pathlib
import tempfile
from unittest import mock

from django.conf import settings
from django.test import TestCase

from accounts.models import User
from cycling_site import skins
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


class DevelopmentReloadTests(TestCase):
    """runserver picks up an edited skin template without a restart."""

    def test_the_skins_folder_is_watched(self):
        reloader = mock.Mock()
        skins.watch_skin_templates(reloader)
        reloader.watch_dir.assert_called_once_with(settings.SKINS_DIR, "**/templates/**/*")

    def test_an_edited_skin_template_clears_the_template_cache_instead_of_restarting(self):
        edited = settings.SKINS_DIR / "ubt" / "templates" / "base.html"
        with mock.patch("django.template.autoreload.reset_loaders") as reset:
            self.assertTrue(skins.reset_on_skin_template(None, edited))
        reset.assert_called_once()

    def test_anything_else_is_left_to_django(self):
        for path in (settings.SKINS_DIR / "ubt" / "skin.css", settings.BASE_DIR / "home" / "models.py"):
            with self.subTest(path=path), mock.patch("django.template.autoreload.reset_loaders") as reset:
                self.assertIsNone(skins.reset_on_skin_template(None, path))
                reset.assert_not_called()
