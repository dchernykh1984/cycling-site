from django.shortcuts import render
from django.utils.translation import gettext as _


def virtual_ride(request):
    """The virtual ride: a self-contained trainer page (static/trainer/alatau.html) in the site's frame."""
    return render(
        request,
        "trainer/virtual_ride.html",
        {
            "meta_title": _("Virtual ride"),
            "meta_description": _("Ride Almaty's routes on an indoor trainer."),
        },
    )
