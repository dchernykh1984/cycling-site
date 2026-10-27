from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def virtual_ride(request):
    """The virtual ride: a self-contained trainer page (static/trainer/alatau.html) in the site's frame.

    The framed page saves rides and rides together through /api/v1/virtual-ride/ with the member's
    session, so it needs the CSRF cookie to send along -- set here even if nothing else on the page
    asked for it.
    """
    return render(
        request,
        "trainer/virtual_ride.html",
        {
            "meta_title": _("Virtual ride"),
            "meta_description": _("Ride Almaty's routes on an indoor trainer."),
        },
    )
