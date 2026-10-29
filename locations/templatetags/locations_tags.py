from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_locations_map_url():
    from locations.models import LocationsMapPage

    # As the news and knowledge links do: with no locale row for the active or the default language the
    # header falls back to any live map page, rather than failing every page that carries it (#385).
    try:
        page = LocationsMapPage.objects.live().filter(locale=Locale.get_active()).first()
    except Locale.DoesNotExist:
        page = None
    if page is None:
        page = LocationsMapPage.objects.live().first()
    return page.url if page else None
