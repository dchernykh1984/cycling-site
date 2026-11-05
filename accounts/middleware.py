"""The privacy policy, asked of a member whose account no sign-up form made (issue #438)."""

from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

from cycling_site.middleware import SiteLocaleMiddleware

#: Pages a member who has not answered yet still opens: the question, the policy and the terms it
#: leads to, and signing out.
OPEN_PAGES = frozenset({"account_privacy_consent", "privacy_policy", "terms_of_use", "account_logout"})


class PrivacyConsentMiddleware:
    """Send a member whose account Google, GitHub or Strava made to the sign-up form's question -- the
    privacy policy -- before any other page, until they answer it. Members from before the question
    are never sent: only a new account a provider made waits for an answer."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.privacy_consent_pending and self._asks_first(request.path_info):
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{reverse('account_privacy_consent')}?{query}")
        return self.get_response(request)

    @staticmethod
    def _asks_first(path: str) -> bool:
        # The API, the admin and files answer their own clients; an address that is no page is a 404.
        if path.startswith(SiteLocaleMiddleware.LANGUAGE_FREE_PREFIXES):
            return False
        try:
            return resolve(path).url_name not in OPEN_PAGES
        except Resolver404:
            return False
