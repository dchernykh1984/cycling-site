"""The skins under skins/ (cycling_site/skins.py) and the hook that keeps their manifests ASCII."""

import json

import pytest
from django.test import TestCase
from django.utils.translation import override

from cycling_site import skins
from scripts.escape_skin_manifests import main as escape_manifests


class RegistryTests(TestCase):
    def test_every_folder_is_a_valid_skin_and_light_and_dark_are_there(self):
        registry = skins.registry()
        self.assertEqual([registry["light"].mode, registry["dark"].mode], ["light", "dark"])
        self.assertEqual(list(registry)[:2], ["light", "dark"])

    def test_a_skin_is_named_in_the_readers_language(self):
        dark = skins.registry()["dark"]
        for lang in skins.LANGUAGES:
            with self.subTest(lang=lang), override(lang):
                self.assertEqual(dark.name, dark.names[lang])
        self.assertEqual(dark.names["en"], "Dark")

    def test_the_base_stylesheets_are_light_then_dark(self):
        self.assertEqual(skins.base_stylesheets(), ["skins/light/skin.css", "skins/dark/skin.css"])

    def test_every_page_links_them(self):
        html = self.client.get("/ru/privacy/").content.decode()
        self.assertLess(html.index("css/cycling_site"), html.index("skins/light/skin"))
        self.assertLess(html.index("skins/light/skin"), html.index("skins/dark/skin"))


def _folder(tmp_path, manifest, css=True):
    folder = tmp_path / "custom"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    if css:
        (folder / "skin.css").write_text("")
    return folder


# "Dark" in Russian, spelled by code point: source files stay ASCII.
DARK = "".join(map(chr, (0x422, 0x451, 0x43C, 0x43D, 0x430, 0x44F)))
GOOD = {"name": {"ru": "R", "kk": "K", "en": "E"}, "mode": "dark", "order": 30}


def test_a_folder_loads_as_a_skin_keyed_by_its_name(tmp_path):
    skin = skins._load(_folder(tmp_path, GOOD))
    assert (skin.key, skin.mode, skin.order) == ("custom", "dark", 30)


@pytest.mark.parametrize(
    ("manifest", "css", "complaint"),
    [
        ({**GOOD, "mode": "sepia"}, True, "mode must be one of"),
        ({**GOOD, "name": {"ru": "R", "en": "E"}}, True, "no name in kk"),
        (GOOD, False, "no skin.css"),
    ],
)
def test_a_broken_skin_is_refused_with_the_reason(tmp_path, manifest, css, complaint):
    with pytest.raises(ValueError, match=complaint):
        skins._load(_folder(tmp_path, manifest, css))


def test_the_hook_escapes_cyrillic_once_and_then_passes(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"name": {"ru": DARK}}, ensure_ascii=False))
    assert escape_manifests([str(manifest)]) == 1
    assert manifest.read_text().isascii()
    assert json.loads(manifest.read_text())["name"]["ru"] == DARK
    assert escape_manifests([str(manifest)]) == 0


def test_the_hook_fails_on_broken_json(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{")
    assert escape_manifests([str(manifest)]) == 1


def test_the_real_manifests_are_already_escaped():
    for folder in skins.SKINS_DIR.iterdir():
        if folder.is_dir():
            assert escape_manifests([str(folder / "manifest.json")]) == 0, folder
