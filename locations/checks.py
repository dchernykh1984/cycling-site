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


@checks.register()
def map_services_can_be_filled_in(app_configs, **kwargs):
    """A catalogue entry an event page cannot fill in would turn every event with a start point into an
    error page. Refused at startup instead: ``migrate`` stops on an error, so such a deploy never goes live.
    """
    errors = []
    for key, service in settings.MAP_SERVICES.items():
        try:
            str(service["label"])
            service["url"].format(lat="0", lng="0", zoom=1)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            errors.append(
                checks.Error(
                    f"MAP_SERVICES[{key!r}] cannot be filled in ({exc!r}): it needs a label, and a url that"
                    " names nothing but {lat}, {lng} and {zoom}.",
                    obj=key,
                    id="locations.E001",
                )
            )
    return errors
