"""The skins a reader can pick from: one folder each under skins/ at the repository root.

A skin is skins/<key>/manifest.json -- its name in the three languages, the Bootstrap colour mode it
builds on (light or dark) and its place in the list -- next to skins/<key>/skin.css. The folder name
is the key that a profile or a cookie stores, so a folder is never renamed.

The light and dark skins are the base modes: their stylesheets hold everything that differs between
the two modes and are always on the page, so switching between them needs no reload, and any skin
built on a mode starts from that mode's rules.
"""

import functools
import json
from dataclasses import dataclass

from django.conf import settings
from django.utils.translation import get_language

SKINS_DIR = settings.BASE_DIR / "skins"
MODES = ("light", "dark")
LANGUAGES = ("ru", "kk", "en")


@dataclass(frozen=True)
class Skin:
    key: str
    mode: str
    order: int
    names: dict

    @property
    def name(self) -> str:
        return self.names.get((get_language() or "")[:2]) or self.names["en"]

    @property
    def stylesheet(self) -> str:
        return f"skins/{self.key}/skin.css"


def _load(folder) -> Skin:
    manifest = json.loads((folder / "manifest.json").read_text())
    skin = Skin(key=folder.name, mode=manifest["mode"], order=manifest["order"], names=manifest["name"])
    if skin.mode not in MODES:
        raise ValueError(f"{folder.name}: mode must be one of {MODES}, not {skin.mode!r}")
    missing = [lang for lang in LANGUAGES if not skin.names.get(lang)]
    if missing:
        raise ValueError(f"{folder.name}: no name in {', '.join(missing)}")
    if not (folder / "skin.css").is_file():
        raise ValueError(f"{folder.name}: no skin.css")
    return skin


@functools.cache
def registry() -> dict[str, Skin]:
    """Every skin by key, in the order the list shows them."""
    skins = sorted((_load(folder) for folder in SKINS_DIR.iterdir() if folder.is_dir()), key=lambda s: s.order)
    return {skin.key: skin for skin in skins}


def base_stylesheets() -> list[str]:
    return [registry()[mode].stylesheet for mode in MODES]
