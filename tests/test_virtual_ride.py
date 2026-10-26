"""The "Virtual ride" tab: the trainer page in the site's frame, linked from the navbar in every skin."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

TRAINER = Path(settings.BASE_DIR) / "trainer" / "static" / "trainer" / "alatau.html"


class VirtualRideTests(TestCase):
    def test_the_page_frames_the_trainer_in_every_language(self):
        for lang in ("ru", "kk", "en"):
            with translation_override(lang):
                url = reverse("virtual_ride")
                title = gettext("Virtual ride")
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, lang)
            self.assertContains(response, '<iframe class="virtual-ride-frame"')
            self.assertContains(response, "trainer/alatau.html")
            self.assertContains(response, title)

    def test_the_frame_may_reach_the_trainer_over_bluetooth_and_keep_the_screen_on(self):
        self.assertContains(self.client.get(reverse("virtual_ride")), 'allow="bluetooth; screen-wake-lock; fullscreen"')

    def test_the_trainer_file_ships_with_the_site(self):
        self.assertIn("<!doctype html>", TRAINER.read_text(encoding="utf-8")[:100].lower())

    def test_the_page_is_in_the_sections_sitemap(self):
        self.assertIn(reverse("virtual_ride"), self.client.get("/sitemap-sections.xml").content.decode())


class VirtualRideNavigationTests(TestCase):
    def test_every_skin_links_the_tab_in_its_navbar(self):
        for skin in ("light", "dark", "orange"):
            with override_settings(DEFAULT_SKIN=skin):
                html = self.client.get(reverse("calendar")).content.decode()
            self.assertIn(f'href="{reverse("virtual_ride")}"', html, skin)
