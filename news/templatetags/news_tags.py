from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_news_index_url():
    from news.models import NewsIndexPage

    page = NewsIndexPage.objects.live().filter(locale=Locale.get_active()).first()
    if page is None:
        page = NewsIndexPage.objects.live().first()
    return page.url if page else None
