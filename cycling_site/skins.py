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
import re
from contextvars import ContextVar
from dataclasses import dataclass, replace

from django.conf import settings
from django.template.loaders.cached import Loader as CachedLoader
from django.template.loaders.filesystem import Loader as FilesystemLoader
from django.utils.translation import get_language

MODES = ("light", "dark")
LANGUAGES = ("ru", "kk", "en")
# Where a guest's choice is kept: the server has to know it before it renders the page.
COOKIE = "skin"


@dataclass(frozen=True)
class Skin:
    key: str
    mode: str
    order: int
    names: dict
    # skins/<key>/skin.js, when the skin brings behaviour of its own.
    has_script: bool = False

    @property
    def name(self) -> str:
        return self.names.get((get_language() or "")[:2]) or self.names["en"]

    @property
    def is_base(self) -> bool:
        """Light or dark: always on the page, so switching between them needs no reload."""
        return self.key in MODES

    @property
    def stylesheet(self) -> str:
        return f"skins/{self.key}/skin.css"

    @property
    def script(self) -> str:
        return f"skins/{self.key}/skin.js"


def _load(folder) -> Skin:
    from accounts.models import User

    # The key is what a profile stores; a longer one would be offered and then fail to save.
    longest = User._meta.get_field("theme").max_length or 0
    if len(folder.name) > longest:
        raise ValueError(f"{folder.name}: a key is at most {longest} characters")
    manifest = json.loads((folder / "manifest.json").read_text())
    skin = Skin(key=folder.name, mode=manifest["mode"], order=manifest["order"], names=manifest["name"])
    if skin.mode not in MODES:
        raise ValueError(f"{folder.name}: mode must be one of {MODES}, not {skin.mode!r}")
    missing = [lang for lang in LANGUAGES if not skin.names.get(lang)]
    if missing:
        raise ValueError(f"{folder.name}: no name in {', '.join(missing)}")
    if not (folder / "skin.css").is_file():
        raise ValueError(f"{folder.name}: no skin.css")
    _check_fonts(folder)
    return replace(skin, has_script=(folder / "skin.js").is_file())


FONT_FACE = re.compile(r"@font-face\s*{([^}]*)}", re.IGNORECASE)
FAMILY = re.compile(r"font-family\s*:\s*['\"]?([^;'\"]+)", re.IGNORECASE)
URL = re.compile(r"url\(\s*['\"]?([^)'\"]+)", re.IGNORECASE)


def _check_fonts(folder) -> None:
    """A skin's own fonts: named for the skin, present in the folder, and under a licence.

    The prefix keeps two designers' "Heading" from ever meaning each other's font.
    """
    faces = FONT_FACE.findall((folder / "skin.css").read_text())
    for face in faces:
        found = FAMILY.search(face)
        family = found.group(1).strip() if found else ""
        if not family.startswith(f"skin-{folder.name}-"):
            raise ValueError(f"{folder.name}: a font of its own is named skin-{folder.name}-<role>, not {family!r}")
        for url in URL.findall(face):
            if not url.startswith(("data:", "http:", "https:")) and not (folder / url).is_file():
                raise ValueError(f"{folder.name}: no font file {url}")
    if faces and not any((folder / "fonts").glob("*LICEN[CS]E*")) and not any((folder / "fonts").glob("OFL*")):
        raise ValueError(f"{folder.name}: fonts/ needs the fonts' licence (LICENSE or OFL.txt)")


@functools.cache
def registry() -> dict[str, Skin]:
    """Every skin by key, in the order the list shows them."""
    folders = settings.SKINS_DIR.iterdir()
    skins = sorted((_load(folder) for folder in folders if folder.is_dir()), key=lambda s: s.order)
    return {skin.key: skin for skin in skins}


def stylesheets(skin: Skin) -> list[str]:
    """The light and dark rules, always; a skin of its own after them, only while it is chosen."""
    base = [registry()[mode].stylesheet for mode in MODES]
    return base if skin.key in MODES else [*base, skin.stylesheet]


def resolve(key) -> Skin:
    """The skin a stored key names; a key no folder answers to any more falls back to the default."""
    skins = registry()
    return skins.get(key) or skins[settings.DEFAULT_SKIN]


def chosen(request) -> Skin:
    """The skin this request is drawn in: a member's profile, a guest's cookie."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return resolve(user.theme)
    return resolve(request.COOKIES.get(COOKIE))


# The skin of the request being answered, for the template loaders below; None outside a request
# (e-mails, management commands), which then get the site's own templates.
current_skin: ContextVar[str | None] = ContextVar("current_skin", default=None)


class SkinMiddleware:
    """Tell the template loaders which skin this request is drawn in."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_skin.set(chosen(request).key)
        try:
            return self.get_response(request)
        finally:
            current_skin.reset(token)


class SkinLoader(FilesystemLoader):
    """skins/<key>/templates/ of the current skin: a template there replaces the site's own."""

    def get_dirs(self):
        key = current_skin.get()
        if key is None or key in MODES:
            return []
        return [settings.SKINS_DIR / key / "templates"]


class SkinCachedLoader(CachedLoader):
    """Django's template cache, with one copy of a template per skin."""

    def cache_key(self, template_name, skip=None):
        return f"{current_skin.get() or ''}:{super().cache_key(template_name, skip)}"


# runserver reloads a changed template only from the folders the loaders always read; a skin's
# templates are read per request, so without these a designer would restart it after every edit.
def watch_skin_templates(sender, **kwargs):
    sender.watch_dir(settings.SKINS_DIR, "**/templates/**/*")


def reset_on_skin_template(sender, file_path, **kwargs):
    from django.template.autoreload import reset_loaders

    root = settings.SKINS_DIR
    if root in file_path.parents and "templates" in file_path.relative_to(root).parts:
        reset_loaders()
        return True  # The cache is cleared; there is no need to restart the server.
    return None


def connect_autoreload():
    from django.utils.autoreload import autoreload_started, file_changed

    autoreload_started.connect(watch_skin_templates, dispatch_uid="skins-watch")
    file_changed.connect(reset_on_skin_template, dispatch_uid="skins-reset")
