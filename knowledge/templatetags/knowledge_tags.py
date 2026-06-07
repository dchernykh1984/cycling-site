from django import template
from wagtail.models import Locale

register = template.Library()


@register.simple_tag
def get_knowledge_index_url():
    from knowledge.models import KnowledgeIndexPage

    page = KnowledgeIndexPage.objects.live().filter(locale=Locale.get_active()).first()
    if page is None:
        page = KnowledgeIndexPage.objects.live().first()
    return page.url if page else None
