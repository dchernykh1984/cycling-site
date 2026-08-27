from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.sitemaps import views as sitemap_views
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import URLPattern, URLResolver, include, path, re_path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from accounts.views import set_language as accounts_set_language
from api.router import api as ninja_api
from cycling_site.sitemaps import (
    CompetitionSitemap,
    KnowledgeArticleSitemap,
    NewsArticleSitemap,
    WagtailPagesSitemap,
)
from search import views as search_views


def favicon_redirect(request):
    """Browsers probe the site root for /favicon.ico; point them at the static file.
    Resolved lazily so it also works with hashed names under ManifestStaticFilesStorage."""
    from django.templatetags.static import static

    return redirect(static("favicon.ico"))


def indexnow_key_file(request, key):
    """`/<key>.txt`, which is how Bing, Yandex and Seznam verify that whoever submits URLs for
    this host controls it. Any other name is a 404, so the file exists only for the real key."""
    from django.http import Http404

    configured = (getattr(settings, "INDEXNOW_KEY", "") or "").strip()
    if not configured or key != configured:
        raise Http404
    return HttpResponse(configured, content_type="text/plain")


def robots_txt(request):
    base_url = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    sitemap_url = f"{base_url}/sitemap.xml" if base_url else request.build_absolute_uri("/sitemap.xml")
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {sitemap_url}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def serve_media(request, path):
    """Serve user-uploaded media through the WSGI app.

    On CodeRed Cloud /media/ requests reach the app instead of being served from disk,
    and Django only auto-serves media under DEBUG, so production media 404s (the Wagtail
    catch-all below turns it into a page-not-found) without this route. MEDIA_ROOT is read
    per request so tests can override it. This routes every media hit through a worker --
    acceptable for this low-traffic site; a web server/CDN would be preferable at scale.
    """
    from django.views.static import serve as django_serve

    return django_serve(request, path, document_root=settings.MEDIA_ROOT)


sitemaps = {
    "wagtail": WagtailPagesSitemap,
    "knowledge": KnowledgeArticleSitemap,
    "news": NewsArticleSitemap,
    "competitions": CompetitionSitemap,
}

# Machine-facing addresses, and the ones a language prefix would only get in the way of: the API,
# both admins, the media and the files a crawler asks for by exact name.
urlpatterns: list[URLPattern | URLResolver] = [
    path("django-admin/", admin.site.urls),
    path("api/v1/", ninja_api.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("i18n/set_language/", accounts_set_language, name="set_language"),
    path("favicon.ico", favicon_redirect, name="favicon"),
    path("robots.txt", robots_txt, name="robots_txt"),
    re_path(
        r"^(?P<key>[A-Za-z0-9\-]{8,128})\.txt$",
        indexnow_key_file,
        name="indexnow_key_file",
    ),
    # An index over per-section files rather than one flat list: the competitions section alone
    # is 500+ URLs and grows with every approved event, and a section can be re-fetched on its own.
    path(
        "sitemap.xml",
        sitemap_views.index,
        {"sitemaps": sitemaps, "sitemap_url_name": "sitemap_section"},
        name="sitemap",
    ),
    path(
        "sitemap-<section>.xml",
        sitemap_views.sitemap,
        {"sitemaps": sitemaps},
        name="sitemap_section",
    ),
    # Serve user-uploaded media in every environment (must precede the Wagtail catch-all).
    re_path(r"^media/(?P<path>.*)$", serve_media, name="media"),
]

# Everything a reader sees lives under a language prefix: /ru/..., /kk/..., /en/....
#
# Each locale is then an address of its own -- indexable, linkable, and unambiguous about which
# language it is in. Before this the three languages shared one path and were told apart by a
# cookie, so a crawler only ever saw one of them and two thirds of the site did not exist as far
# as search was concerned.
#
# The unprefixed URL keeps working: LocaleMiddleware answers it with a 302 to the prefix matching
# the reader's own cookie or Accept-Language, so a link pasted into a chat still opens in each
# reader's language, and every link ever shared still resolves.
urlpatterns += i18n_patterns(
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("knowledge/", include("knowledge.urls")),
    path("locations/", include("locations.urls")),
    path("news/", include("news.urls")),
    path("calendar/", include("calendar_app.urls")),
    path("", include("protocols.urls")),
    path("", include("registrations.urls")),
    path("search/", search_views.search, name="search"),
    path("", include("home.urls")),
    path("", include(wagtail_urls)),  # must be last
    prefix_default_language=True,
)


if settings.DEBUG:  # pragma: no cover - dev-only static serving; tests force DEBUG=False
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
