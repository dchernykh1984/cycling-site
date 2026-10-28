import re
import secrets
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from accounts.access import needs_email_confirmation

from . import strava
from .models import StravaConnection

# What the Strava round trip keeps in the session: the state it must come back with and where to go after
_PENDING = "virtual_ride_strava"


@ensure_csrf_cookie
def virtual_ride(request):
    """The virtual ride: a self-contained trainer page (static/trainer/alatau.html) in the site's frame.

    The framed page saves rides and rides together through /api/v1/virtual-ride/ with the member's
    session, so it needs the CSRF cookie to send along -- set here even if nothing else on the page
    asked for it. The framed page is told the reader's language and, from a shared link, the group
    race to open.
    """
    query = {"lang": get_language()}
    group = request.GET.get("group", "")
    if re.fullmatch(r"[0-9]{1,12}", group):
        query["group"] = group
    return render(
        request,
        "trainer/virtual_ride.html",
        {
            "meta_title": _("Virtual ride"),
            "meta_description": _("Ride Almaty's routes on an indoor trainer."),
            "trainer_query": urlencode(query),
        },
    )


def _profile_card() -> str:
    return reverse("account_profile") + "#virtual-rides"


@login_required
def strava_connect(request):
    """Send the member to Strava to allow uploading their virtual rides (``activity:write``)."""
    if needs_email_confirmation(request.user) or not strava.available():
        raise Http404
    back = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = _profile_card()
    state = secrets.token_urlsafe(24)
    request.session[_PENDING] = {"state": state, "next": back}
    return redirect(strava.authorize_url(request.build_absolute_uri(reverse("virtual_ride_strava_callback")), state))


@login_required
def strava_callback(request):
    """Strava sends the member back here with a code, or with the reason there is none."""
    pending = request.session.pop(_PENDING, None) or {}
    back = pending.get("next") or _profile_card()
    if not pending.get("state") or not constant_time_compare(request.GET.get("state", ""), pending["state"]):
        messages.error(request, _("The answer from Strava did not match the request. Try connecting again."))
        return redirect(_profile_card())
    if request.GET.get("error"):
        messages.info(request, _("Strava was not connected: your rides stay on this site."))
        return redirect(back)
    if "activity:write" not in request.GET.get("scope", "").split(","):
        messages.warning(
            request,
            _(
                "Strava did not allow uploading activities, so rides are not sent there. "
                "Connect again and keep that permission on."
            ),
        )
        return redirect(back)
    try:
        strava.connect(request.user, request.GET.get("code", ""))
    except strava.StravaError:
        messages.error(request, _("Strava could not be reached. Try connecting again later."))
        return redirect(back)
    messages.success(request, _("Strava is connected: every ride you finish goes there as a virtual ride."))
    return redirect(back)


@login_required
@require_POST
def strava_disconnect(request):
    connection = StravaConnection.objects.filter(user=request.user).first()
    if connection is not None:
        strava.disconnect(connection)
    messages.success(request, _("Strava is disconnected: rides are no longer sent there."))
    return redirect(_profile_card())
