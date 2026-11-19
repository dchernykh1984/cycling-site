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
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_POST

from accounts.access import needs_email_confirmation

from . import intervals, services, strava
from .models import IntervalsConnection, StravaConnection

# What the Strava round trip keeps in the session: the state it must come back with and where to go after
_PENDING = "virtual_ride_strava"


@ensure_csrf_cookie
def virtual_ride(request):
    """The virtual ride: the trainer page (static/trainer/alatau.html and its alatau/ files) in a frame.

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


def _services_card() -> str:
    return reverse("account_profile") + "#virtual-rides-services"


_SERVICE_NAMES = {services.STRAVA: "Strava", services.INTERVALS: "intervals.icu"}


@login_required
@require_POST
def service_sending(request, service):
    """The profile's box "Send my rides to ...": off keeps the service connected and sends nothing."""
    if service not in services.SERVICES or needs_email_confirmation(request.user):
        raise Http404
    on = request.POST.get("send_rides") == "on"
    if services.set_sending(request.user, service, on):
        name = {"service": _SERVICE_NAMES[service]}
        if on:
            messages.success(request, _("Your rides now go to %(service)s.") % name)
        else:
            messages.success(request, _("Your rides no longer go to %(service)s; it stays connected.") % name)
    return redirect(_services_card())


@sensitive_post_parameters("api_key")
@login_required
@require_POST
@sensitive_variables("key")
def intervals_connect(request):
    """The member's own API key: checked with intervals.icu, then kept sealed and never shown again."""
    if needs_email_confirmation(request.user) or not intervals.available():
        raise Http404
    key = request.POST.get("api_key", "")[:200]
    try:
        intervals.connect(request.user, key, request.POST.get("send_rides") == "on")
    except intervals.TooManyTriesError:
        messages.error(request, _("Too many keys tried in a row: wait a few minutes, then give yours again."))
    except intervals.IntervalsError as exc:
        # the reason itself is English, for the logs and the API: the member reads what to do next
        if exc.revoked or not key.strip():
            messages.error(request, _("intervals.icu does not accept this key. Check it and try again."))
        else:
            messages.error(request, _("intervals.icu could not check the key just now. Try connecting again later."))
    else:
        messages.success(request, _("intervals.icu is connected."))
    return redirect(_services_card())


@login_required
@require_POST
def intervals_disconnect(request):
    connection = IntervalsConnection.objects.filter(user=request.user).first()
    if connection is not None:
        intervals.disconnect(connection)
    messages.success(request, _("intervals.icu is disconnected: the key is deleted from this site."))
    return redirect(_services_card())
