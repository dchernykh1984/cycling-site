from django.http import Http404
from django.shortcuts import render
from django.utils import translation
from django.utils.translation import check_for_language


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
        if hasattr(request, "user") and request.user.is_authenticated:
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
