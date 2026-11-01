from django import template

from cycling_site.page_mixins import active_locale_page_url

register = template.Library()


@register.simple_tag
def get_locations_map_url():
    from locations.models import LocationsMapPage

    return active_locale_page_url(LocationsMapPage)
