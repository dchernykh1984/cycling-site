"""The virtual ride's trainer page as the tests read it: the page and, in its order, the files it loads."""

import json
import re
from pathlib import Path

from django.conf import settings

PAGE = Path(settings.BASE_DIR) / "trainer" / "static" / "trainer" / "alatau.html"


def local_files() -> list[Path]:
    """The page's own stylesheets and scripts, in the order the page loads them (not a CDN's)."""
    html = PAGE.read_text(encoding="utf-8")
    refs = re.findall(r'<(?:script src|link rel="stylesheet" href)="(?![a-z]+:|//)([^"]+)"', html)
    return [PAGE.parent / ref for ref in refs]


def scripts() -> list[str]:
    """The code the page runs, in its order: its own files and any script written into the page."""
    code = []
    for src, written in re.findall(
        r'<script(?: src="([^"]*)")?>(.*?)</script>', PAGE.read_text(encoding="utf-8"), re.DOTALL
    ):
        if not src:
            code.append(written)
        elif not re.match(r"[a-z]+:|//", src):
            code.append((PAGE.parent / src).read_text(encoding="utf-8"))
    return code


def source() -> str:
    """The page, then the code it runs, in the order it runs it."""
    return "\n".join([PAGE.read_text(encoding="utf-8"), *scripts()])


def texts() -> dict:
    """The page's words, a ``const TEXT_RU = {...};`` per language, as Python: ``{"ru": {...}, ...}``."""
    found = re.findall(r"^const TEXT_(RU|KK|EN) = (\{.*?^\});$", source(), re.DOTALL | re.MULTILINE)
    return {lang.lower(): json.loads(block) for lang, block in found}
