"""Turning a stored rich-text body into one line a search result can show.

Knowledge articles and news are written as HTML with inline images; a meta description needs plain
prose, short, and cut on a word rather than mid-syllable. Every one of these pages used to carry
the same site-wide sentence, so nothing told a search engine what any of them was about.
"""

import re

from django.utils.html import strip_tags
from django.utils.text import Truncator

# A data URI can be tens of thousands of characters and carries no words at all.
_IMG = re.compile(r"<img[^>]*>", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")

MAX_DESCRIPTION_CHARS = 200


def summarize(*sources: str | None, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    """The first real prose among ``sources``, flattened and cut to ``limit`` on a word boundary."""
    for source in sources:
        if not source:
            continue
        text = _WHITESPACE.sub(" ", strip_tags(_IMG.sub(" ", source))).strip()
        if text:
            return Truncator(text).chars(limit, truncate="...")
    return ""
