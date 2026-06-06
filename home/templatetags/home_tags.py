from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_about_url():
    from home.models import AboutPage

    page = AboutPage.objects.live().filter(locale=Locale.get_active()).first()
    if page is None:
        page = AboutPage.objects.live().first()
    return page.url if page else None
