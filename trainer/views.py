import re
from urllib.parse import urlencode

from django.shortcuts import render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie


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
