"""A skin of one's own for tests: the real light and dark, plus one made up in a temporary folder.

Real skins exist only as the designers add them, so the tests that exercise a skin's own
stylesheet, script and templates build one instead.
"""

import json
import shutil
from contextlib import contextmanager

from django.conf import settings
from django.template import engines
from django.test import override_settings

from cycling_site import skins

TRIAL_NAMES = {"ru": "Trial RU", "kk": "Trial KK", "en": "Trial"}


def _reset_caches():
    skins.registry.cache_clear()
    for loader in engines["django"].engine.template_loaders:
        loader.reset()


@contextmanager
def trial_skin(root, *, mode="dark", css="", script=None, templates=None):
    """Serve light, dark and a "trial" skin from root while the block runs."""
    # The base modes, and the skin the suite runs in (E2E_SKIN): the default has to stay a skin
    # the registry knows, or every page would fail to resolve it.
    for kept in {*skins.MODES, settings.DEFAULT_SKIN} - {"trial"}:
        shutil.copytree(settings.SKINS_DIR / kept, root / kept)
    folder = root / "trial"
    folder.mkdir()
    manifest = {"name": TRIAL_NAMES, "mode": mode, "order": 30}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (folder / "skin.css").write_text(css)
    if script is not None:
        (folder / "skin.js").write_text(script)
    for path, text in (templates or {}).items():
        target = folder / "templates" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    static_dirs = [d for d in settings.STATICFILES_DIRS if not (isinstance(d, tuple) and d[0] == "skins")]
    with override_settings(SKINS_DIR=root, STATICFILES_DIRS=[*static_dirs, ("skins", root)]):
        _reset_caches()
        try:
            yield
        finally:
            _reset_caches()
