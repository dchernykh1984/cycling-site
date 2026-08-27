from django.contrib.sitemaps import Sitemap
from wagtail.contrib.sitemaps.sitemap_generator import Sitemap as WagtailSitemap

from calendar_app.models import Competition
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle


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
        return obj.updated_at


class NewsArticleSitemap(Sitemap):
    """News articles, on the same footing as knowledge articles."""

    changefreq = "monthly"

    def items(self):
        return NewsArticle.objects.filter(is_deleted=False, is_hidden=False)

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.published_at


class CompetitionSitemap(Sitemap):
    """Every publicly visible competition -- the bulk of the site, and until now the part of it
    search engines were never told about.

    ``limit`` splits the list across several <sitemap> files under the index. The protocol caps a
    single file at 50 000 URLs and we are far below that, but a page of a few hundred is quicker to
    fetch and to re-fetch, and the split costs nothing.

    A past event keeps its page and stays listed: it is the record of a race that happened, and it
    is what someone searching for last year's results is looking for.
    """

    limit = 500
    changefreq = "weekly"

    def items(self):
        return Competition.objects.filter(
            status=Competition.Status.APPROVED, is_hidden=False, is_deleted=False
        ).order_by("-date_start", "pk")

    def location(self, obj):
        return obj.get_absolute_url()

    def priority(self, obj):
        # An event still to come is the one worth crawling first; a finished one is an archive page.
        import datetime

        return 0.8 if obj.date_start >= datetime.date.today() else 0.4
