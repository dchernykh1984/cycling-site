"""The one setup hint a reader sees at the top of the page (issue #319).

A visitor who never signs in sees the calendar as everybody sees it -- every sport, every country --
and many leave right there, never learning that the site can be fitted to them. So the page says
so, once, in a single line under the menu:

* not signed in -- sign in, on every page, and it cannot be closed;
* email not confirmed -- until it is, entering races, adding events and commenting are closed, so
  this one cannot be closed either;
* no calendar preferences -- only on the calendar, list and map, where they change what is shown;
* no name, gender or date of birth -- what a race entry needs;
* only one way to sign in -- losing it locks the member out;
* no Strava link -- races that collect one take it from the entry.

The first that applies is shown, never two. A signed-in member may turn each reminder off for good,
one by one; it takes a deliberate click and a confirmation, because a hint closed by reflex is how
someone in Almaty ends up wondering why the calendar is full of races in Spain.

Keep this list in step with the site: a feature that starts depending on something the member sets
up gets a hint here, and one that stops depending on it loses its hint (see the shipping-changes
skill, "Setup hints stay current").
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

#: Hints a member may turn off, in the order they are offered.
DISMISSIBLE = ("preferences", "registration_data", "signin_methods", "strava")

# Where calendar preferences change what is shown.
_CALENDAR_PAGES = {"calendar", "calendar_list", "calendar_map"}


def _url_name(request) -> str:
    match = getattr(request, "resolver_match", None)
    return (match.url_name or "") if match else ""


def on_account_page(request) -> bool:
    """Whether the page is under accounts/ -- sign-in, sign-up, the profile, a password reset, and the
    "continue with Google" step of each sign-in service.

    Matched by path rather than by route names, because allauth names the service pages after the
    service (google_login, strava_login...) and a new service must not slip past.
    """
    match = getattr(request, "resolver_match", None)
    if match is None:
        return False
    first, _, rest = (match.route or "").partition("/")
    route = rest if first in {code for code, _ in settings.LANGUAGES} else match.route or ""
    return route.startswith("accounts/")


def _quiet_here(request) -> bool:
    """Pages where a hint would only repeat the page.

    The account pages: the hint would ask to sign in someone who is signing in, or point at the page
    it is on. The race entry form: it already names what the profile is missing, right above its
    button.
    """
    match = getattr(request, "resolver_match", None)
    return on_account_page(request) or getattr(match, "view_name", "") == "registrations:register"


def _has_preferences(user) -> bool:
    return (
        user.preferred_directions.exists()
        or user.preferred_disciplines.exists()
        or user.preferred_locations.exists()
        or user.preferred_event_types.exists()
    )


def _has_registration_data(user) -> bool:
    return bool(user.first_name and user.last_name and user.gender and user.birth_date)


def _has_a_second_way_in(user) -> bool:
    from accounts.views import signin_methods

    return signin_methods(user)["method_count"] > 1


def current_hint(request) -> dict | None:
    """The hint to show on this page, or None."""
    if _quiet_here(request):
        return None
    user = request.user
    if not user.is_authenticated:
        return {
            "key": "sign_in",
            # Back to the page they were reading, filters and all.
            "login_url": f"{reverse('account_login')}?{urlencode({'next': request.get_full_path()})}",
            "signup_url": reverse("account_signup"),
        }
    from accounts.access import needs_email_confirmation

    if needs_email_confirmation(user):
        return {"key": "confirm_email", "url": reverse("account_profile")}
    dismissed = set(user.dismissed_hints or [])
    checks = (
        (
            "preferences",
            lambda: _url_name(request) not in _CALENDAR_PAGES or _has_preferences(user),
            f"{reverse('account_profile_edit')}#calendar-defaults",
        ),
        ("registration_data", lambda: _has_registration_data(user), reverse("account_profile_edit")),
        ("signin_methods", lambda: _has_a_second_way_in(user), f"{reverse('account_profile')}#signin-methods"),
        ("strava", lambda: bool(user.strava_link), f"{reverse('account_profile_edit')}#strava-link"),
    )
    for key, is_done, url in checks:
        # Checked in order and lazily: the sign-in check reads the database, and most members never
        # get that far down the list on a given page.
        if key in dismissed or is_done():
            continue
        return {"key": key, "url": url, "dismissible": True}
    return None
