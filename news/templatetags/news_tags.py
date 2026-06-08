from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_news_index_url():
    from news.models import NewsIndexPage

    try:
        active_locale = Locale.get_active()
    except Locale.DoesNotExist:
        return None
    page = NewsIndexPage.objects.live().filter(locale=active_locale).first()
    if page is None:
        page = NewsIndexPage.objects.live().first()
    return page.url if page else None
