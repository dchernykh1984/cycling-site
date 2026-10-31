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


def source() -> str:
    """The page, then its scripts: what the browser runs, in the order it runs it."""
    scripts = [path.read_text(encoding="utf-8") for path in local_files() if path.suffix == ".js"]
    return "\n".join([PAGE.read_text(encoding="utf-8"), *scripts])


def texts() -> dict:
    """The page's own dictionary, ``const TEXT = { ru: {...}, kk: {...}, en: {...} }``, as Python."""
    block = re.search(r"^const TEXT = (\{.*?^\});$", source(), re.DOTALL | re.MULTILINE)
    assert block is not None
    return json.loads(re.sub(r"^  (ru|kk|en): \{", r'  "\1": {', block.group(1), flags=re.MULTILINE))
