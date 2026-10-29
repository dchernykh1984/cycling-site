"""Startup checks for the places' settings."""

from django.conf import settings
from django.core import checks


@checks.register()
def map_link_services_are_known(app_configs, **kwargs):
    """A deployment that names a map service the catalogue does not describe would lose it silently."""
    from locations.maps import offered_services

    return [
        checks.Warning(
            f"MAP_LINK_SERVICES names {key!r}, which MAP_SERVICES does not describe; it is not offered.",
            id="locations.W001",
        )
        for key in offered_services()
        if key not in settings.MAP_SERVICES
    ]
