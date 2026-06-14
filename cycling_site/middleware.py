from django.conf import settings
from django.http import Http404
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

    Additionally, when Wagtail raises Http404 because a page doesn't exist in the
    current locale, this middleware retries the request using the default locale so
    that untranslated pages degrade gracefully instead of showing a 404.
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

        current_lang = translation.get_language()
        default_lang = settings.LANGUAGE_CODE
        if not current_lang or current_lang == default_lang:
            return None

        from wagtail.views import serve as wagtail_serve

        path = request.path_info.lstrip("/")
        # Wagtail caches the route result on the request; clear it so the
        # retry with the default locale re-routes through the correct page tree.
        request.__dict__.pop("_wagtail_route_for_request", None)
        translation.activate(default_lang)
        request.LANGUAGE_CODE = default_lang
        try:
            return wagtail_serve(request, path)
        except Http404:
            return None
        finally:
            translation.activate(current_lang)
            request.LANGUAGE_CODE = current_lang
