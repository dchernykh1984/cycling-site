"""The "Virtual ride" tab: the trainer page in the site's frame, linked from the navbar in every skin."""

import re

from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from tests import trainer_page


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

    def test_the_trainer_is_told_the_language_of_the_page(self):
        for lang in ("ru", "kk", "en"):
            with translation_override(lang):
                url = reverse("virtual_ride")
            # the frame and the full-screen link both open the trainer in the reader's language
            self.assertContains(self.client.get(url), f"trainer/alatau.html?lang={lang}", count=2)

    def test_a_link_to_a_group_race_reaches_the_trainer(self):
        with translation_override("kk"):
            url = reverse("virtual_ride")
        self.assertContains(self.client.get(url, {"group": "12"}), "alatau.html?lang=kk&amp;group=12", count=2)
        for junk in ("abc", "12x", "\u00b2", "1" * 13):
            self.assertContains(self.client.get(url, {"group": junk}), 'alatau.html?lang=kk"', count=2)

    def test_the_frame_may_use_bluetooth_keep_the_screen_on_and_share_a_link(self):
        self.assertContains(
            self.client.get(reverse("virtual_ride")),
            'allow="bluetooth; screen-wake-lock; fullscreen; clipboard-write; web-share"',
        )

    def test_the_trainer_file_ships_with_the_site(self):
        self.assertIn("<!doctype html>", trainer_page.PAGE.read_text(encoding="utf-8")[:100].lower())

    def test_every_text_of_the_trainer_exists_in_every_language(self):
        source = trainer_page.source()
        texts = trainer_page.texts()
        self.assertEqual(set(texts), {"ru", "kk", "en"})
        self.assertEqual(set(texts["kk"]), set(texts["ru"]))
        self.assertEqual(set(texts["en"]), set(texts["ru"]))
        used = set(re.findall(r"\bt[rn]?\('([\w.]+)'", source)) | set(
            re.findall(r'data-t(?:-label|-alt)?="([\w.]+)"', source)
        )
        self.assertEqual(used - set(texts["ru"]), set(), "a text the page asks for is missing")
        self.assertEqual(set(texts["ru"]) - used, set(), "a text nothing asks for")

    def test_every_file_the_trainer_loads_ships_with_the_site(self):
        files = trainer_page.local_files()
        self.assertTrue(files)
        for path in files:
            name = path.relative_to(trainer_page.PAGE.parent.parent).as_posix()
            self.assertIsNotNone(finders.find(name), name)

    def test_the_trainer_talks_to_the_site_in_one_place(self):
        # a ride is ridden in the browser: what reaches the site goes through Site.req, to the trainer's API
        code = "\n".join(trainer_page.scripts())
        self.assertEqual(re.findall(r"\bfetch\(", code), ["fetch("])
        self.assertIsNone(re.search(r"sendBeacon|XMLHttpRequest|WebSocket|EventSource", code))
        self.assertIn("const API_BASE = '/api/v1/virtual-ride';", code)

    def test_the_page_is_in_the_sections_sitemap(self):
        self.assertIn(reverse("virtual_ride"), self.client.get("/sitemap-sections.xml").content.decode())


class VirtualRideNavigationTests(TestCase):
    def test_every_skin_links_the_tab_in_its_navbar(self):
        for skin in ("light", "dark", "orange", "ubt-dark"):
            with override_settings(DEFAULT_SKIN=skin):
                html = self.client.get(reverse("calendar")).content.decode()
            self.assertIn(f'href="{reverse("virtual_ride")}"', html, skin)
