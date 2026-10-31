"""The virtual ride's trainer page as the tests read it: the page and, in its order, the files it loads."""

import json
import re
from pathlib import Path

from django.conf import settings

PAGE = Path(settings.BASE_DIR) / "trainer" / "static" / "trainer" / "alatau.html"


def _attribute(attributes: str, name: str) -> str | None:
    found = re.search(rf'(?<![\w-]){name}="([^"]*)"', attributes)
    return found.group(1) if found else None


def _own(ref: str) -> bool:
    """A file of the page's own, not a CDN's: no scheme, not //."""
    return not re.match(r"[a-z]+:|//", ref)


def local_files() -> list[Path]:
    """The page's own stylesheets and scripts, in the order the page loads them."""
    refs = []
    for tag, attributes in re.findall(r"<(script|link)\b([^>]*)>", PAGE.read_text(encoding="utf-8")):
        if tag == "link" and _attribute(attributes, "rel") != "stylesheet":
            continue
        ref = _attribute(attributes, "src" if tag == "script" else "href")
        if ref and _own(ref):
            refs.append(ref)
    return [PAGE.parent / ref for ref in refs]


def scripts() -> list[str]:
    """The code the page runs, in its order: its own files and any script written into the page."""
    code = []
    for attributes, written in re.findall(
        r"<script\b([^>]*)>(.*?)</script>", PAGE.read_text(encoding="utf-8"), re.DOTALL
    ):
        src = _attribute(attributes, "src")
        if src is None:
            code.append(written)
        elif _own(src):
            code.append((PAGE.parent / src).read_text(encoding="utf-8"))
    return code


def source() -> str:
    """The page, then the code it runs, in the order it runs it."""
    return "\n".join([PAGE.read_text(encoding="utf-8"), *scripts()])


def texts() -> dict:
    """The page's words, a ``const TEXT_RU = {...};`` per language, as Python: ``{"ru": {...}, ...}``."""
    found = re.findall(r"^const TEXT_(RU|KK|EN) = (\{.*?^\});$", source(), re.DOTALL | re.MULTILINE)
    return {lang.lower(): json.loads(block) for lang, block in found}
