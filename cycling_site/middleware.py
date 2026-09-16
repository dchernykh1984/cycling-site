from urllib.parse import urlsplit

from django.http import Http404
from django.middleware.locale import LocaleMiddleware
from django.shortcuts import render
from django.utils import translation
from django.utils.cache import add_never_cache_headers
from django.utils.translation import check_for_language, get_language_from_path


class LocaleFallbackMiddleware:
    """Activate the user's preferred language for every request.

    LocaleMiddleware reads the language from the LANGUAGE_COOKIE_NAME cookie
    (and Accept-Language) but knows nothing about our custom User.preferred_language
    field.  This middleware fills that gap: for authenticated users it overrides
    whatever LocaleMiddleware activated with the stored preference so the language
    stays consistent across devices and sessions.

    For anonymous users LocaleMiddleware already handles the cookie correctly, so
    no action is taken here.

    Additionally, when any view raises Http404, this middleware renders the
    custom 404.html template directly.  This bypasses Django's technical debug
    404 page so the real error page is shown in all environments including
    DEBUG=True.  Wagtail pages that do not exist in the active locale are
    intentionally left as 404: the knowledge index only lists articles in the
    current locale, so surfacing a foreign-locale article via fallback would
    show content the index page does not link to.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # A language prefix in the address is an explicit request for that language, and it wins:
        # /en/calendar/ has to be English even for a reader whose profile says Russian, or the
        # three addresses are not really three addresses and a crawler is served the wrong one.
        # The stored preference still decides which prefix an unprefixed URL redirects to.
        if hasattr(request, "user") and request.user.is_authenticated and not get_language_from_path(request.path_info):
            pref = request.user.preferred_language
            if pref:
                if check_for_language(pref):
                    translation.activate(pref)
                    request.LANGUAGE_CODE = pref

        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, Http404):
            return None
        return render(request, "404.html", status=404)


class SiteLocaleMiddleware(LocaleMiddleware):
    """LocaleMiddleware, minus the language redirect on addresses that have no language.

    With i18n_patterns in place, LocaleMiddleware answers any 404 by retrying the same path under
    a language prefix. That is what makes an unprefixed page redirect to the reader's own language,
    and it is exactly wrong for the API, the admin and uploaded files: a client asking for a
    competition that does not exist must be told 404, not sent to /ru/api/v1/... to be told the
    same thing one round trip later.
    """

    #: Addresses that are the same in every language, so a prefix means nothing there.
    LANGUAGE_FREE_PREFIXES = (
        "/api/v1/",
        "/admin/",
        "/django-admin/",
        "/documents/",
        "/media/",
        "/static/",
        "/i18n/",
    )

    def process_response(self, request, response):
        if request.path_info.startswith(self.LANGUAGE_FREE_PREFIXES):
            return response
        response = super().process_response(request, response)
        if self._is_language_redirect(request, response):
            # An address with no language of its own answers differently to every reader: the same
            # "/" sends one person to /ru/ and the next to /en/, off their cookie, their profile and
            # their Accept-Language. Carrying no cache directive at all, it is fair game for a
            # browser's heuristics -- and Safari keeps redirects and honours "Vary: Cookie" only in
            # part, so an iPhone that was sent to /en/ once goes on sending itself there long after
            # the reader has chosen Russian, until the cache is cleared by hand. Two readers have
            # reported exactly that. The choice is made per request; it must not be stored.
            #
            # Django's own never-cache headers rather than a hand-written "no-store": they say the
            # same thing in every dialect a cache might read -- no-cache, must-revalidate, private
            # and an Expires in the past alongside it -- and a browser this stubborn is exactly the
            # reader that needs to be told twice.
            add_never_cache_headers(response)
        return response

    @staticmethod
    def _is_language_redirect(request, response) -> bool:
        """Whether this response is the redirect that picks a language for an address without one."""
        if response.status_code not in (301, 302):
            return False
        if get_language_from_path(request.path_info):
            return False
        location = response.headers.get("Location", "")
        return bool(get_language_from_path(urlsplit(location).path))
