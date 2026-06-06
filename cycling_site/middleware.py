import re

from django.http import HttpResponseRedirect

_LOCALE_PREFIX_RE = re.compile(r"^/(?P<lang>[a-z]{2})/(?P<path>.*)$")
_FALLBACK_ORDER = ("ru", "en", "kk")


class LocaleFallbackMiddleware:
    """Redirect locale-prefixed 404s to the first available fallback locale.

    With prefix_default_language=False, Russian URLs have no prefix (/path/),
    while Kazakh and English use /kk/ and /en/ prefixes. When a translated
    page does not exist for the requested locale, redirect to ru -> en -> kk
    in that order, skipping the locale that just returned 404.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
            fallback_url = f"/{path}" if lang == "ru" else f"/{lang}/{path}"
            return HttpResponseRedirect(fallback_url)

        return response
