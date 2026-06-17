from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import URLPattern, URLResolver, include, path, re_path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap as wagtail_sitemap
from wagtail.documents import urls as wagtaildocs_urls

from accounts.views import set_language as accounts_set_language
from api.router import api as ninja_api
from cycling_site.sitemaps import WagtailPagesSitemap
from search import views as search_views


def favicon_redirect(request):
    """Browsers probe the site root for /favicon.ico; point them at the static file.
    Resolved lazily so it also works with hashed names under ManifestStaticFilesStorage."""
    from django.templatetags.static import static

    return redirect(static("favicon.ico"))


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
}

urlpatterns: list[URLPattern | URLResolver] = [
    path("django-admin/", admin.site.urls),
    path("api/v1/", ninja_api.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("i18n/set_language/", accounts_set_language, name="set_language"),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("knowledge/", include("knowledge.urls")),
    path("locations/", include("locations.urls")),
    path("news/", include("news.urls")),
    path("calendar/", include("calendar_app.urls")),
    path("", include("protocols.urls")),
    path("", include("registrations.urls")),
    path("search/", search_views.search, name="search"),
    path("favicon.ico", favicon_redirect, name="favicon"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", wagtail_sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    # Serve user-uploaded media in every environment (must precede the Wagtail catch-all).
    re_path(r"^media/(?P<path>.*)$", serve_media, name="media"),
    path("", include("home.urls")),
    path("", include(wagtail_urls)),  # must be last
]


if settings.DEBUG:  # pragma: no cover - dev-only static serving; tests force DEBUG=False
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
