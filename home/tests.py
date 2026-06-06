import importlib

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from wagtail.models import Locale, Page, Site
from wagtail.test.utils import WagtailPageTestCase
from wagtail_localize.fields import SynchronizedField

from home.models import HomePage


class HomeSetUpTests(WagtailPageTestCase):
    """
    Tests for basic page structure setup and HomePage creation.
    """

    def test_root_create(self):
        root_page = Page.objects.get(pk=1)
        self.assertIsNotNone(root_page)

    def test_homepage_create(self):
        root_page = Page.objects.get(pk=1)
        homepage = HomePage(title="Home")
        root_page.add_child(instance=homepage)
        self.assertTrue(HomePage.objects.filter(title="Home").exists())


class HomeTests(WagtailPageTestCase):
    """
    Tests for homepage functionality and rendering.
    """

    def setUp(self):
        """
        Create a homepage instance for testing.
        """
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)

    def test_homepage_is_renderable(self):
        self.assertPageIsRenderable(self.homepage)

    def test_homepage_template_used(self):
        response = self.client.get(self.homepage.url)
        self.assertTemplateUsed(response, "home/home_page.html")


class LocalizationTests(WagtailPageTestCase):
    """Tests for Phase 2 localization setup."""

    def test_default_language_is_russian(self):
        self.assertEqual(settings.LANGUAGE_CODE, "ru")

    def test_three_languages_configured(self):
        codes = [code for code, _ in settings.LANGUAGES]
        self.assertIn("ru", codes)
        self.assertIn("kk", codes)
        self.assertIn("en", codes)

    def test_wagtail_i18n_enabled(self):
        self.assertTrue(settings.WAGTAIL_I18N_ENABLED)

    def test_ru_locale_exists_in_db(self):
        self.assertTrue(Locale.objects.filter(language_code="ru").exists())

    def test_kk_locale_exists_in_db(self):
        self.assertTrue(Locale.objects.filter(language_code="kk").exists())

    def test_en_locale_exists_in_db(self):
        self.assertTrue(Locale.objects.filter(language_code="en").exists())

    def test_homepage_slug_is_synchronized(self):
        synchronized_slugs = [
            f.field_name for f in HomePage.override_translatable_fields if isinstance(f, SynchronizedField)
        ]
        self.assertIn("slug", synchronized_slugs)


class LocaleMigrationLegacyTests(TestCase):
    """Verify that 0003_locales handles pre-Phase-2 databases with en-us locale."""

    def test_migration_renames_legacy_en_us_to_ru(self):
        from django.apps import apps as django_apps

        migration_mod = importlib.import_module("home.migrations.0003_locales")

        # Simulate legacy state: rename "ru" -> "en-us" (as it was before Phase 2).
        # TestCase wraps each test in a savepoint, so this is rolled back after.
        ru = Locale.objects.filter(language_code="ru").first()
        if ru:
            ru.language_code = "en-us"
            ru.save()
        Locale.objects.filter(language_code__in=["kk", "en"]).delete()

        migration_mod.create_locales(django_apps, None)

        self.assertTrue(Locale.objects.filter(language_code="ru").exists())
        self.assertFalse(Locale.objects.filter(language_code="en-us").exists())
        self.assertTrue(Locale.objects.filter(language_code="kk").exists())
        self.assertTrue(Locale.objects.filter(language_code="en").exists())


class LocaleFallbackMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_middleware(self, status):
        from cycling_site.middleware import LocaleFallbackMiddleware

        return LocaleFallbackMiddleware(lambda r: HttpResponse(status=status))

    def test_redirects_kk_404_to_ru(self):
        mw = self._make_middleware(404)
        request = self.factory.get("/kk/some-page/")
        request.path_info = "/kk/some-page/"
        response = mw(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/some-page/")

    def test_redirects_en_404_to_ru(self):
        mw = self._make_middleware(404)
        request = self.factory.get("/en/events/")
        request.path_info = "/en/events/"
        response = mw(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/events/")

    def test_does_not_redirect_on_200(self):
        mw = self._make_middleware(200)
        request = self.factory.get("/kk/some-page/")
        request.path_info = "/kk/some-page/"
        response = mw(request)
        self.assertEqual(response.status_code, 200)

    def test_does_not_redirect_ru_404(self):
        mw = self._make_middleware(404)
        request = self.factory.get("/missing-page/")
        request.path_info = "/missing-page/"
        response = mw(request)
        self.assertEqual(response.status_code, 404)


class AboutPageTests(WagtailPageTestCase):
    def setUp(self):
        from home.models import AboutPage

        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite2", root_page=root_page, is_default_site=True)
        home = HomePage(title="Home")
        root_page.add_child(instance=home)
        self.about = AboutPage(title="About")
        home.add_child(instance=self.about)

    def test_about_page_is_renderable(self):
        self.assertPageIsRenderable(self.about)

    def test_about_page_template_used(self):
        response = self.client.get(self.about.url)
        self.assertTemplateUsed(response, "home/about_page.html")

    def test_about_page_slug_is_synchronized(self):
        from home.models import AboutPage

        synchronized_slugs = [
            f.field_name for f in AboutPage.override_translatable_fields if isinstance(f, SynchronizedField)
        ]
        self.assertIn("slug", synchronized_slugs)
