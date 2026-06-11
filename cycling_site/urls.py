from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import URLPattern, URLResolver, include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap as wagtail_sitemap
from wagtail.documents import urls as wagtaildocs_urls

from accounts.views import set_language as accounts_set_language
from cycling_site.sitemaps import WagtailPagesSitemap
from search import views as search_views


def robots_txt(request):
    base_url = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    sitemap_url = f"{base_url}/sitemap.xml" if base_url else request.build_absolute_uri("/sitemap.xml")
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {sitemap_url}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


sitemaps = {
    "wagtail": WagtailPagesSitemap,
}

urlpatterns: list[URLPattern | URLResolver] = [
    path("django-admin/", admin.site.urls),
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
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", wagtail_sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("home.urls")),
    path("", include(wagtail_urls)),  # must be last
]


if settings.DEBUG:  # pragma: no cover - dev-only static serving; tests force DEBUG=False
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
