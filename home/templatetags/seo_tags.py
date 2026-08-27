"""Template helpers for the parts of a page search engines read rather than people."""

from django.conf import settings
from django.template import Library
from django.urls import translate_url
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
    current = request.get_full_path()
    alternates = []
    for code, _name in settings.LANGUAGES:
        translated = translate_url(current, code)
        if translated == current and code != get_language():
            # Nothing to translate: this URL is the same in every language.
            return []
        alternates.append((code, request.build_absolute_uri(translated)))
    return alternates
