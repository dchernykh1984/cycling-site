class LocaleFallbackMiddleware:
    """Activate the user's preferred language for every request.

    LocaleMiddleware reads the language from the LANGUAGE_COOKIE_NAME cookie
    (and Accept-Language) but knows nothing about our custom User.preferred_language
    field.  This middleware fills that gap: for authenticated users it overrides
    whatever LocaleMiddleware activated with the stored preference so the language
    stays consistent across devices and sessions.

    For anonymous users LocaleMiddleware already handles the cookie correctly, so
    no action is taken here.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "user") and request.user.is_authenticated:
            pref = request.user.preferred_language
            if pref:
                from django.utils import translation
                from django.utils.translation import check_for_language

                if check_for_language(pref):
                    translation.activate(pref)
                    request.LANGUAGE_CODE = pref

        return self.get_response(request)
