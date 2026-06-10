from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_knowledge_index_url():
    from knowledge.models import KnowledgeIndexPage

    try:
        active_locale = Locale.get_active()
    except Locale.DoesNotExist:
        active_locale = None

    page = None
    if active_locale:
        page = KnowledgeIndexPage.objects.live().filter(locale=active_locale).first()
    if page is None:
        page = KnowledgeIndexPage.objects.live().first()
    return page.url if page else None
