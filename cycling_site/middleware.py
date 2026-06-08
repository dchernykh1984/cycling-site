import re

from django.conf import settings
from django.http import HttpResponseRedirect

# Derived at startup from LANGUAGE_CODE (the default/unprefixed language) and LANGUAGES.
# Using settings avoids hardcoding language codes that must be kept in sync manually.
_default_lang = settings.LANGUAGE_CODE.split("-")[0]
_prefixed_langs = [code.split("-")[0] for code, _ in settings.LANGUAGES if code.split("-")[0] != _default_lang]
_prefixed_pattern = "|".join(re.escape(c) for c in _prefixed_langs)

_LOCALE_PREFIX_RE = re.compile(rf"^/(?P<lang>{_prefixed_pattern})/(?P<path>.*)$")
_HAS_LANG_PREFIX_RE = re.compile(rf"^/({_prefixed_pattern})/")
_FALLBACK_ORDER = (_default_lang, *_prefixed_langs)

# URL prefixes that are registered in the regular urlpatterns (NOT inside i18n_patterns).
# Language can be activated safely for these paths: URL resolution does not involve
# LocalePrefixPattern and does not depend on the active language code.
#
# Paths NOT in this list go through i18n_patterns (Wagtail pages, /search/, /kk/...).
# For those paths the URL itself encodes the language; activating a non-default language
# before URL resolution would make LocalePrefixPattern demand /kk/... prefix and return 404.
_NON_I18N_PATH_RE = re.compile(
    r"^/(django-admin|admin|documents|i18n|accounts|knowledge|news|calendar|"
    r"api|protocols|competitions)/"
)


class LocaleFallbackMiddleware:
    """Redirect locale-prefixed 404s to the first available fallback locale.

    With prefix_default_language=False, Russian URLs have no prefix (/path/),
    while Kazakh and English use /kk/ and /en/ prefixes. When a translated
    page does not exist for the requested locale, redirect to ru -> en -> kk
    in that order, skipping the locale that just returned 404.

    Russian unprefixed 404s (/path/ not found) are not handled here -- there is
    no safe fallback because redirecting to /en/path/ would cause a redirect
    loop if that page is also missing (/en/path/ 404 -> redirect to /path/ -> loop).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Re-apply language preference for non-prefixed, non-i18n URL paths.
        #
        # LocaleMiddleware with prefix_default_language=False forces LANGUAGE_CODE for
        # any URL that lacks a language prefix, completely ignoring the cookie.  We
        # override that here for paths that are in regular urlpatterns (calendar, news,
        # knowledge, etc.) so both anonymous and authenticated users see their chosen
        # language there.
        #
        # We must NOT activate a non-default language for paths handled by i18n_patterns
        # (Wagtail pages, /search/).  Those paths rely on URL-prefix detection: if
        # get_language() returns 'kk' when the URL is '/', LocalePrefixPattern demands
        # the '/kk/' prefix and raises a 404.
        #
        # Do NOT call translation.deactivate() after get_response -- LocaleMiddleware
        # reads get_language() in process_response to set Content-Language.
        path_info = request.path_info
        if not _HAS_LANG_PREFIX_RE.match(path_info) and _NON_I18N_PATH_RE.match(path_info):
            from django.utils import translation
            from django.utils.translation import check_for_language

            pref: str | None = None
            if hasattr(request, "user") and request.user.is_authenticated:
                pref = request.user.preferred_language or None
            if not pref:
                # Anonymous user: read the cookie set by Django's set_language view.
                pref = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)

            if pref and check_for_language(pref):
                translation.activate(pref)
                request.LANGUAGE_CODE = pref

        response = self.get_response(request)

        if response.status_code != 404:
            return response

        match = _LOCALE_PREFIX_RE.match(request.path_info)
        if not match:
            return response  # ru URL has no prefix -- no fallback to try

        current_lang = match.group("lang")
        path = match.group("path")

        for lang in _FALLBACK_ORDER:
            if lang == current_lang:
                continue
            fallback_url = f"/{path}" if lang == _default_lang else f"/{lang}/{path}"
            return HttpResponseRedirect(fallback_url)

        return response
