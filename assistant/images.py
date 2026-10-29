"""Pictures in a rich text, kept out of the model's prompt and put back where its answer keeps them.

A picture pasted into the editor is a base64 data URI of hundreds of kilobytes: thousands of tokens on
every turn, for nothing the model needs to read, and the reply's sanitising would drop it besides. The
model sees a short mark instead, ``<img src="image:N">``, keeps it where the picture belongs, and the
original comes back in its place. A picture the model adds on its own is not the site's, and goes.
"""

from __future__ import annotations

import re

_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_MARK = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']image:(\d+)["'][^>]*>""", re.IGNORECASE)


def hide(html: str, images: list[str]) -> str:
    """``html`` with each picture as its mark; the originals are added to ``images`` in order."""

    def mark(match: re.Match) -> str:
        images.append(match.group(0))
        return f'<img src="image:{len(images)}">'

    return _IMG.sub(mark, html)


def restore(html: str, images: list[str]) -> str:
    """``html`` with each mark back as its picture, and every other picture gone."""

    def original(match: re.Match) -> str:
        number = int(match.group(1))
        return images[number - 1] if 0 < number <= len(images) else ""

    marks_only = _IMG.sub(lambda match: match.group(0) if _MARK.fullmatch(match.group(0)) else "", html)
    return _MARK.sub(original, marks_only)
