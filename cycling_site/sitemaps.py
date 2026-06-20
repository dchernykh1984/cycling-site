from django.contrib.sitemaps import Sitemap
from wagtail.contrib.sitemaps.sitemap_generator import Sitemap as WagtailSitemap

from knowledge.models import KnowledgeArticle


class WagtailPagesSitemap(WagtailSitemap):
    """Sitemap covering all live, public Wagtail pages across all locales."""


class KnowledgeArticleSitemap(Sitemap):
    """Knowledge articles are a plain model (not Wagtail pages), so they need their own
    sitemap entry; only visible, non-deleted articles are listed."""

    changefreq = "monthly"

    def items(self):
        return KnowledgeArticle.objects.filter(is_deleted=False, is_hidden=False)

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.published_at
