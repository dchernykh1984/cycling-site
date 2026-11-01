from django import template

from cycling_site.page_mixins import active_locale_page_url

register = template.Library()


@register.simple_tag
def get_knowledge_index_url():
    from knowledge.models import KnowledgeIndexPage

    return active_locale_page_url(KnowledgeIndexPage)
