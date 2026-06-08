from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from accounts.views import set_language as accounts_set_language
from search import views as search_views

urlpatterns: list[URLPattern | URLResolver] = [
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("i18n/set_language/", accounts_set_language, name="set_language"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("knowledge/", include("knowledge.urls")),
    path("news/", include("news.urls")),
    path("calendar/", include("calendar_app.urls")),
    path("", include("protocols.urls")),
    path("", include("registrations.urls")),
]


if settings.DEBUG:  # pragma: no cover - dev-only static serving; tests force DEBUG=False
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += i18n_patterns(
    path("search/", search_views.search, name="search"),
    path("", include(wagtail_urls)),  # must be last inside i18n_patterns
    prefix_default_language=False,
)
