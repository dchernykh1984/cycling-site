import re

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from calendar_app.models import Competition
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle

# /ru/, /kk/ or /en/ at the start of a path.
_LANGUAGE_PREFIX = re.compile(r"^/[a-z]{2}(?:-[a-z]+)?/")


class WagtailPagesSitemap(Sitemap):
    """The live, public Wagtail pages -- home, map, news, knowledge base -- in every language.

    Wagtail's own generator lists a page at the one address its locale gives it, so the home page and
    the section pages went into the sitemap as /ru/... only, while /kk/ and /en/ serve them too. Here
    each page is listed once per language with the other two as alternates, the same as everything
    else in the index. Only the default locale's tree is read: a translated copy of a page, should
    one exist, is the same address under another prefix, not a page of its own.
    """

    changefreq = "weekly"
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        from wagtail.models import Locale, Page

        pages = Page.objects.live().public().filter(depth__gt=1).order_by("path")
        try:
            pages = pages.filter(locale=Locale.get_default())
        except Locale.DoesNotExist:
            pass
        return [page for page in pages.specific() if page.get_url()]

    def location(self, page):
        from django.utils.translation import get_language

        # page.get_url() carries the page's own locale prefix (/ru/map/); the sitemap asks for the
        # address in the language it is listing, so swap the prefix for that one.
        path = _LANGUAGE_PREFIX.sub("/", page.get_url())
        return f"/{get_language()}{path}"

    def lastmod(self, page):
        return page.last_published_at


class SectionPagesSitemap(Sitemap):
    """The calendar's own views, which are views rather than Wagtail pages and were in no sitemap.

    The month grid, the list and the start-point map are where most visitors land; the city and
    discipline lists (CalendarFilterSitemap) are only their filtered versions.
    """

    changefreq = "daily"
    priority = 0.8
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        return ["calendar", "calendar_list", "calendar_map", "gallery_index", "virtual_ride"]

    def location(self, name):
        return reverse(name)


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
            status=Competition.Status.APPROVED, is_hidden=False, invite_only=False, is_deleted=False
        ).order_by("-date_start", "pk")

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        # When the event went public. Competition keeps no edit time of its own, and the approval is
        # the moment its page appeared; better a date than none, which leaves the crawler guessing.
        return obj.approved_at

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

        regions, places, kinds = landing_filters()
        return (
            [("location", region.pk) for region in regions]
            + [("location", place.pk) for place in places]
            + [("discipline", kind.pk) for kind in kinds]
        )

    def location(self, item):
        parameter, pk = item
        return f"{reverse('calendar_list')}?{parameter}={pk}"


class GalleryAlbumSitemap(Sitemap):
    """Every public photo album: the page a search for last year's race photos should land on."""

    changefreq = "monthly"
    priority = 0.5
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        from gallery.models import Album

        # An album with no photos yet is an empty page; an engine files it as a soft 404.
        return Album.objects.public().filter(photos__isnull=False).distinct().order_by("-date", "pk")

    def location(self, album):
        return album.get_absolute_url()

    def lastmod(self, album):
        return album.updated_at
