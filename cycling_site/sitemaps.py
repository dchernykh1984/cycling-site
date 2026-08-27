from django.contrib.sitemaps import Sitemap
from django.urls import reverse
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
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        return KnowledgeArticle.objects.filter(is_deleted=False, is_hidden=False)

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.updated_at


class NewsArticleSitemap(Sitemap):
    """News articles, on the same footing as knowledge articles."""

    changefreq = "monthly"
    i18n = True
    alternates = True
    x_default = True

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
    # One entry per language, each pointing at the other two.
    i18n = True
    alternates = True
    x_default = True

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


class CalendarFilterSitemap(Sitemap):
    """The filtered lists that are pages in their own right: a city, or a discipline.

    `/calendar/list/?location=2` has always been server-rendered -- it returns the matching events
    as plain HTML -- but nothing linked it and nothing listed it, so it existed only for someone
    who had already built the filter in the browser. "Competitions in Almaty" is the shape of the
    query people type, and we hold over a thousand cities.
    """

    changefreq = "weekly"
    priority = 0.6
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        from calendar_app.listing_seo import landing_filters

        places, kinds = landing_filters()
        return [("location", place.pk) for place in places] + [("discipline", kind.pk) for kind in kinds]

    def location(self, item):
        parameter, pk = item
        return f"{reverse('calendar_list')}?{parameter}={pk}"
