"""Template helpers for the parts of a page search engines read rather than people."""

import re
from urllib.parse import urlsplit

from django.conf import settings
from django.template import Library
from django.urls import Resolver404, resolve, translate_url
from django.utils.safestring import mark_safe
from django.utils.translation import get_language

register = Library()


@register.simple_tag(takes_context=True)
def language_alternates(context):
    """This page's address in each language, for `<link rel="alternate" hreflang=...>`.

    Returns an empty list for an address that has no per-language form (the sitemap, the API),
    where declaring alternates would claim three addresses that are in fact one.
    """
    request = context.get("request")
    if request is None:
        return []
    # A page may name another address as the one it is (canonical_path): its alternates follow it.
    current = context.get("canonical_path") or request.get_full_path()
    alternates = []
    for code, _name in settings.LANGUAGES:
        translated = translate_url(current, code)
        if translated == current and code != get_language():
            # Nothing to translate: this URL is the same in every language.
            return []
        alternates.append((code, request.build_absolute_uri(translated)))
    return alternates


# An href that is a path on this site: starts with one slash (two would be another host).
_SITE_HREF = re.compile(r'(\bhref=")(/(?!/)[^"]*)(")')


@register.filter
def localized_links(html):
    """Give the links in a text an author wrote the reader's language prefix (/calendar/1/ -> /ru/calendar/1/).

    Every reader-facing address carries its language, and one without it answers with a redirect --
    which a search engine files as "page with redirect" and counts against the page linking there.
    Texts written before the prefixes, and by hand since, still link the bare form. Rewritten here as
    the page is drawn, so nothing stored changes and a text keeps working in all three languages.
    Addresses served without a language (media, documents, the API, the sitemap) and ones that
    already carry one are left alone. The text is already sanitised; this only edits hrefs.
    """
    language = get_language()
    prefixes = tuple(f"/{code}/" for code, _name in settings.LANGUAGES)

    def prefix(match):
        path = match.group(2)
        if path.startswith(prefixes) or path.rstrip("/") in {p.rstrip("/") for p in prefixes}:
            return match.group(0)
        try:
            resolve(urlsplit(path).path)
        except Resolver404:
            return f"{match.group(1)}/{language}{path}{match.group(3)}"
        return match.group(0)  # served as it is, without a language

    return mark_safe(_SITE_HREF.sub(prefix, str(html)))  # noqa: S308 -- input is the sanitised text it was before
