"""The "Virtual ride" tab: the trainer page in the site's frame, linked from the navbar in every skin."""

import json
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

TRAINER = Path(settings.BASE_DIR) / "trainer" / "static" / "trainer" / "alatau.html"


def trainer_texts(source: str) -> dict:
    """The page's own dictionary, ``const TEXT = { ru: {...}, kk: {...}, en: {...} }``, as Python."""
    block = re.search(r"^const TEXT = (\{.*?^\});$", source, re.DOTALL | re.MULTILINE)
    assert block is not None
    return json.loads(re.sub(r"^  (ru|kk|en): \{", r'  "\1": {', block.group(1), flags=re.MULTILINE))


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

    def test_the_frame_may_use_bluetooth_keep_the_screen_on_share_a_link_and_hear_the_microphone(self):
        self.assertContains(
            self.client.get(reverse("virtual_ride")),
            'allow="bluetooth; screen-wake-lock; fullscreen; clipboard-write; web-share; microphone"',
        )

    def test_the_trainer_file_ships_with_the_site(self):
        self.assertIn("<!doctype html>", TRAINER.read_text(encoding="utf-8")[:100].lower())

    def test_every_text_of_the_trainer_exists_in_every_language(self):
        source = TRAINER.read_text(encoding="utf-8")
        texts = trainer_texts(source)
        self.assertEqual(set(texts), {"ru", "kk", "en"})
        self.assertEqual(set(texts["kk"]), set(texts["ru"]))
        self.assertEqual(set(texts["en"]), set(texts["ru"]))
        used = set(re.findall(r"\bt[rn]?\('([\w.]+)'", source)) | set(
            re.findall(r'data-t(?:-label|-alt)?="([\w.]+)"', source)
        )
        self.assertEqual(used - set(texts["ru"]), set(), "a text the page asks for is missing")
        self.assertEqual(set(texts["ru"]) - used, set(), "a text nothing asks for")

    def test_the_page_is_in_the_sections_sitemap(self):
        self.assertIn(reverse("virtual_ride"), self.client.get("/sitemap-sections.xml").content.decode())


class VirtualRideNavigationTests(TestCase):
    def test_every_skin_links_the_tab_in_its_navbar(self):
        for skin in ("light", "dark", "orange"):
            with override_settings(DEFAULT_SKIN=skin):
                html = self.client.get(reverse("calendar")).content.decode()
            self.assertIn(f'href="{reverse("virtual_ride")}"', html, skin)
