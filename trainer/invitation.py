"""The line a ride takes to Strava and intervals.icu: an invitation to ride on this site, and its address.

The words are in the language of the member who rode -- their choice in the profile, else the language
the request came in -- and the address is the virtual ride's page in that language, so whoever follows
it lands on a page in the rider's language. The club is named as the settings name it, never here.
"""

from django.conf import settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext
from wagtail.models import Site


def club_name() -> str:
    """The short name the settings give the club, else its full one, else the site's own name."""
    named = settings.ORGANIZATION_SHORT_NAME or settings.ORGANIZATION_NAME
    if named:
        return named
    site = Site.objects.filter(is_default_site=True).first()
    return (site.site_name or "") if site else ""


def _language(user) -> str:
    for code in (user.preferred_language, translation.get_language()):
        try:
            return translation.get_supported_language_variant(code or "")
        except LookupError:
            continue
    return settings.LANGUAGE_CODE


def invitation(user) -> str:
    """The description of the member's ride: the invitation, then the virtual ride page's address."""
    with translation.override(_language(user)):
        page = settings.SITE_BASE_URL.rstrip("/") + reverse("virtual_ride")
        club = club_name()
        return f"{gettext('Ride with %(club)s!') % {'club': club}}\n{page}" if club else page
