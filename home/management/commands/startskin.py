"""manage.py startskin <key> -- the folder of a new skin, ready to be filled (skins/README.md)."""

import json
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cycling_site import skins

STYLESHEET = """/* {key}: what this skin changes. It is on the page only while the skin is chosen.

   Built on the {mode} mode: everything in skins/{mode}/skin.css applies first, so start by
   overriding its variables, then restyle anything else. */

:root[data-skin="{key}"] {{
    /* --skin-accent: #fc6104; */
}}
"""


class Command(BaseCommand):
    help = "Create skins/<key>/ with a manifest and an empty stylesheet."

    def add_arguments(self, parser):
        parser.add_argument("key", help="lowercase letters, digits and dashes; the folder name, never renamed later")
        parser.add_argument("--mode", choices=skins.MODES, default="light", help="the base mode it builds on")

    def handle(self, *args, key, mode, **options):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", key):
            raise CommandError(f"{key!r}: use lowercase letters, digits and dashes")
        folder = settings.SKINS_DIR / key
        if folder.exists():
            raise CommandError(f"{folder} already exists")
        order = max((skin.order for skin in skins.registry().values()), default=0) + 10
        folder.mkdir()
        manifest = {"name": {"ru": key, "kk": key, "en": key}, "mode": mode, "order": order}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (folder / "skin.css").write_text(STYLESHEET.format(key=key, mode=mode))
        try:
            skins._load(folder)
        except ValueError as error:
            for path in folder.iterdir():
                path.unlink()
            folder.rmdir()
            raise CommandError(str(error)) from None
        skins.registry.cache_clear()
        self.stdout.write(f"Created {folder}: name it in manifest.json, then see skins/README.md.")
