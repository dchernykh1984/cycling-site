import re

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from calendar_app.visibility import public_events
from cycling_site.articles import public
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle

# /ru/, /kk/ or /en/ at the start of a path.
_LANGUAGE_PREFIX = re.compile(r"^/[a-z]{2}(?:-[a-z]+)?/")


class LanguageSitemap(Sitemap):
    """Pages in every language: each listed once per language, with its other languages and an
    x-default as alternates.

    Django writes x-default without the default language's prefix, as for a site that leaves that
    language unprefixed. Every language has its prefix here, and an unprefixed address only redirects
    by the reader's language -- so the sitemap named some 2,400 redirects to Google (#348). x-default
    is the default language's own address instead, the one each page names in its own hreflang links.
    """

    i18n = True
    alternates = True
    x_default = True

    def get_urls(self, page=1, site=None, protocol=None):
        urls = super().get_urls(page=page, site=site, protocol=protocol)
        for url in urls:
            alternates = url.get("alternates", [])
            own = [alt["location"] for alt in alternates if alt["lang_code"] == settings.LANGUAGE_CODE]
            for alt in alternates:
                if alt["lang_code"] == "x-default" and own:
                    alt["location"] = own[0]
        return urls


class WagtailPagesSitemap(LanguageSitemap):
    """The live, public Wagtail pages -- home, map, news, knowledge base -- in every language.

    Wagtail's own generator lists a page at the one address its locale gives it, so the home page and
    the section pages went into the sitemap as /ru/... only, while /kk/ and /en/ serve them too. Here
    each page is listed once per language with the other two as alternates, the same as everything
    else in the index. Only the default locale's tree is read: a translated copy of a page, should
    one exist, is the same address under another prefix, not a page of its own.
    """

    changefreq = "weekly"

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


class SectionPagesSitemap(LanguageSitemap):
    """The calendar's own views, which are views rather than Wagtail pages and were in no sitemap.

    The month grid, the list and the start-point map are where most visitors land; the city and
    discipline lists (CalendarFilterSitemap) are only their filtered versions.
    """

    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["calendar", "calendar_list", "calendar_map", "gallery_index", "virtual_ride"]

    def location(self, name):
        return reverse(name)


class KnowledgeArticleSitemap(LanguageSitemap):
    """Knowledge articles are a plain model (not Wagtail pages), so they need their own
    sitemap entry; only visible, non-deleted articles are listed."""

    changefreq = "monthly"

    def items(self):
        return public(KnowledgeArticle.objects)

    def get_languages_for_item(self, item):
        # An article is written in one language and lives under that prefix: listed once per
        # language, it was one address three times, with alternates naming translations that do not exist.
        return [item.locale]

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.updated_at


class NewsArticleSitemap(LanguageSitemap):
    """News articles, on the same footing as knowledge articles."""

    changefreq = "monthly"

    def items(self):
        return public(NewsArticle.objects)

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.published_at


class CompetitionSitemap(LanguageSitemap):
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
        return public_events().order_by("-date_start", "pk")

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        # The later of its last edit and its approval: an event edited after it went public is read
        # again, and one last edited before the edit time was kept dates from going public (#348).
        return max((moment for moment in (obj.updated_at, obj.approved_at) if moment), default=None)

    def priority(self, obj):
        # An event still to come is the one worth crawling first; a finished one is an archive page.
        import datetime

        return 0.8 if obj.date_start >= datetime.date.today() else 0.4


class CalendarFilterSitemap(LanguageSitemap):
    """The filtered lists that are pages in their own right: a city, or a discipline.

    `/calendar/list/?location=2` has always been server-rendered -- it returns the matching events
    as plain HTML -- but nothing linked it and nothing listed it, so it existed only for someone
    who had already built the filter in the browser. "Competitions in Almaty" is the shape of the
    query people type, and we hold over a thousand cities.
    """

    changefreq = "weekly"
    priority = 0.6

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


class GalleryAlbumSitemap(LanguageSitemap):
    """Every public photo album: the page a search for last year's race photos should land on."""

    changefreq = "monthly"
    priority = 0.5

    def items(self):
        from gallery.models import Album

        # An album with no photos yet is an empty page; an engine files it as a soft 404.
        return Album.objects.public().filter(photos__isnull=False).distinct().order_by("-date", "pk")

    def location(self, album):
        return album.get_absolute_url()

    def lastmod(self, album):
        return album.updated_at
