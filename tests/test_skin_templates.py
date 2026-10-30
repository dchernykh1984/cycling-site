"""A skin's own templates (skins/<key>/templates/) replace the site's for whoever chose the skin."""

import pathlib
import re
import shutil
import tempfile
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings

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


# The skin under test is set here, not taken from DEFAULT_SKIN, which is free to change.
@override_settings(DEFAULT_SKIN="light")
class ChooserReloadTests(TestCase):
    """Light and dark switch in place; going into or out of a skin of its own reloads the page."""

    def _reloading(self):
        html = self.client.get("/ru/news/").content.decode()
        return set(re.findall(r'data-skin-key="([^"]+)"[^>]*data-reload="1"', html))

    def test_from_light_only_the_skin_of_its_own_reloads(self):
        with trial_skin(pathlib.Path(tempfile.mkdtemp())):
            self.assertEqual(self._reloading(), {"trial"})

    def test_from_a_skin_of_its_own_every_choice_reloads(self):
        with trial_skin(pathlib.Path(tempfile.mkdtemp())):
            self.client.cookies[COOKIE] = "trial"
            self.assertEqual(self._reloading(), {"light", "dark", "trial"})


class SuiteSkinTests(TestCase):
    """The trial skin works whichever skin the suite runs in, a designer's included."""

    def test_the_suite_s_own_skin_survives_the_trial_skin(self):
        real = pathlib.Path(tempfile.mkdtemp())
        for base in ("light", "dark"):
            shutil.copytree(settings.SKINS_DIR / base, real / base)
        (real / "review-own").mkdir()
        (real / "review-own" / "manifest.json").write_text(
            '{"name": {"ru": "R", "kk": "K", "en": "E"}, "mode": "light", "order": 30}'
        )
        (real / "review-own" / "skin.css").write_text("")
        with override_settings(SKINS_DIR=real, DEFAULT_SKIN="review-own"):
            with trial_skin(pathlib.Path(tempfile.mkdtemp())):
                response = self.client.get("/ru/news/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-skin="review-own"')


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
            with self.subTest(path=str(path)), mock.patch("django.template.autoreload.reset_loaders") as reset:
                self.assertIsNone(skins.reset_on_skin_template(None, path))
                reset.assert_not_called()


def test_a_skin_s_own_base_keeps_the_site_s_lines_under_the_menu():
    """A skin that replaces base.html still carries what the site says under the menu, or its readers
    never see the moderation queue, a setup hint or the next skin on offer -- and the way back to the
    page after signing in or out."""
    from django.conf import settings

    back = 'name="next" value="{{ request.get_full_path }}"'
    for base in sorted(settings.SKINS_DIR.glob("*/templates/base.html")):
        text = base.read_text()
        for part in ("_moderation_banner.html", "_setup_hint.html", "_skin_offer.html", "sign_in_url", back):
            assert part in text, f"{base.parent.parent.name}: base.html leaves out {part}"
