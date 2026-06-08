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
        # Apply authenticated user's language preference for non-prefixed paths.
        # Prefixed paths (e.g. /kk/..., /en/...) are already handled by LocaleMiddleware
        # via URL inspection and must not be overridden.
        # Do NOT call translation.deactivate() after get_response - LocaleMiddleware
        # (which wraps this one) calls it in process_response and also uses the active
        # language to set the Content-Language header, so deactivating early would
        # produce a wrong header for kk/en preference users.
        if (
            hasattr(request, "user")
            and request.user.is_authenticated
            and request.user.preferred_language
            and not _HAS_LANG_PREFIX_RE.match(request.path_info)
        ):
            from django.utils import translation
            from django.utils.translation import check_for_language

            pref = request.user.preferred_language
            if check_for_language(pref):
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
