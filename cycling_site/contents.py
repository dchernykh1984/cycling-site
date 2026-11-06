"""Anchors on the headings of an article, and a contents list of links to them where its author asked for one.

Knowledge articles and news are rich text written in the editor or sent through the API, and the
sanitiser keeps no id on any tag, so nothing in a text could be linked to. As the page is drawn, every
h2 and h3 gets an id made of its own words -- "2. Participants" becomes ``section-2-participants`` --
the same on every visit, so a link to a section keeps working; the prefix keeps the ids clear of the
page's own. A paragraph holding the marker ``[toc]`` alone becomes the list of those headings, h3
nested under their h2, each a link. Nothing stored changes, and an article without the marker looks
as it did.
"""

import html
import re

from django.utils.html import escape, strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import get_language, gettext, override

#: A paragraph holding the marker alone, as the editor or the API leaves it -- aligned by the editor too
MARKER = re.compile(r"<p(?:\s[^>]*)?>\s*\[toc\]\s*</p>", re.IGNORECASE)
_HEADING = re.compile(r"<(h[23])(\s[^>]*)?>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL)
PREFIX = "section-"


def _words(inner: str) -> str:
    """A heading's text as a reader sees it: no tags, entities read, spaces collapsed."""
    return " ".join(html.unescape(strip_tags(inner)).split())


def with_contents(body: str, language: str | None = None) -> str:
    """``body`` -- a sanitised text -- with an id on every h2 and h3, and its first ``[toc]`` paragraph
    replaced by the contents, titled in ``language`` -- the text's own, where a page shows a text written
    in another (a knowledge article opened at another language's address) --, else the page's. Further
    markers are dropped, and a text without one is left as it was."""
    headings: list[tuple[str, str, str]] = []
    taken: set[str] = set()

    def anchor(match: re.Match) -> str:
        tag, attributes, inner = match.group(1).lower(), match.group(2) or "", match.group(3)
        words = _words(inner)
        base = PREFIX + (slugify(words, allow_unicode=True) or str(len(headings) + 1))
        ident, count = base, 2
        while ident in taken:
            ident, count = f"{base}-{count}", count + 1
        taken.add(ident)
        headings.append((tag, ident, words))
        return f'<{tag}{attributes} id="{escape(ident)}">{inner}</{tag}>'

    text = _HEADING.sub(anchor, str(body))
    if MARKER.search(text):
        with override(language or get_language()):
            contents = _contents(headings)
        text = MARKER.sub(lambda _match: contents, text, count=1)
        text = MARKER.sub("", text)
    return mark_safe(text)  # noqa: S308 -- the sanitised text, with ids and links built from escaped words


def _contents(headings: list[tuple[str, str, str]]) -> str:
    """The headings as nested lists of links; an h3 before any h2 stands at the top level."""
    if not headings:
        return ""
    tree: list[tuple[str, list[str]]] = []
    for tag, ident, words in headings:
        link = f'<a href="#{escape(ident)}">{escape(words)}</a>'
        if tag == "h3" and tree:
            tree[-1][1].append(link)
        else:
            tree.append((link, []))
    items = "".join(
        f"<li>{link}" + (f"<ul>{''.join(f'<li>{sub}</li>' for sub in subs)}</ul>" if subs else "") + "</li>"
        for link, subs in tree
    )
    title = escape(gettext("Contents"))
    return (
        f'<nav class="article-toc" aria-labelledby="article-toc-title">'
        f'<p class="article-toc-title" id="article-toc-title">{title}</p><ul>{items}</ul></nav>'
    )


def without_marker(body: str | None) -> str:
    """The text with no ``[toc]`` paragraph in it, for what reads it as prose: a summary, a feed."""
    return MARKER.sub(" ", body or "")
