from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_locations_map_url():
    from locations.models import LocationsMapPage

    page = LocationsMapPage.objects.live().filter(locale=Locale.get_active()).first()
    if page is None:
        page = LocationsMapPage.objects.live().first()
    return page.url if page else None
