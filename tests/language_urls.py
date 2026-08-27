"""Addressing a page in a particular language, for tests.

Every reader-facing URL now carries a language prefix, and the prefix -- not the Accept-Language
header, not a cookie, not a stored profile preference -- decides which language the page comes
back in. A test that wants the English page has to ask for the English address.
"""

from django.conf import settings

#: Addresses that carry no language prefix at all (see cycling_site.urls).
LANGUAGE_FREE = ("/api/v1/", "/admin/", "/django-admin/", "/documents/", "/media/", "/static/", "/i18n/")


def in_language(url: str, language: str) -> str:
    """The same page, at its address in `language`. A language-free address is returned as is."""
    if url.startswith(LANGUAGE_FREE):
        return url
    known = tuple(f"/{code}/" for code, _name in settings.LANGUAGES)
    if url.startswith(known):
        return f"/{language}/" + url.split("/", 2)[2]
    return f"/{language}{url}"
