import importlib

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from wagtail.models import Locale, Page, Site
from wagtail.test.utils import WagtailPageTestCase
from wagtail_localize.fields import SynchronizedField

from accounts.models import User
from home.models import HomePage, SiteContent


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


class SiteContentModelTests(TestCase):
    def test_str(self):
        SiteContent.objects.filter(pk=1).delete()
        obj = SiteContent.objects.create(pk=1, navbar_title_ru="Test")
        self.assertEqual(str(obj), "Site content")

    def test_load_creates_singleton_if_missing(self):
        from django.core.cache import cache

        from home.models import _SITE_CONTENT_CACHE_KEY

        SiteContent.objects.all().delete()
        cache.delete(_SITE_CONTENT_CACHE_KEY)
        obj = SiteContent.load()
        self.assertEqual(obj.pk, 1)
        self.assertEqual(SiteContent.objects.count(), 1)

    def test_load_returns_existing(self):
        sc = SiteContent.objects.get_or_create(pk=1)[0]
        sc.navbar_title_ru = "TestNavbar"
        sc.save()
        loaded = SiteContent.load()
        self.assertEqual(loaded.navbar_title_ru, "TestNavbar")

    def test_save_always_forces_pk1(self):
        SiteContent.objects.all().delete()
        obj = SiteContent(pk=99, navbar_title_ru="X")
        obj.save()
        self.assertTrue(SiteContent.objects.filter(pk=1).exists())
        self.assertFalse(SiteContent.objects.filter(pk=99).exists())


class HomeEditViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner@test.local",
            email="owner@test.local",
            password="pw",
            role=User.Role.OWNER,
        )
        self.regular = User.objects.create_user(
            username="user@test.local",
            email="user@test.local",
            password="pw",
            role=User.Role.ORGANIZER,
        )
        # is_superuser=True but no OWNER role - should still be denied
        self.superuser_no_role = User.objects.create_superuser(
            username="admin@test.local", email="admin@test.local", password="pw"
        )
        SiteContent.objects.get_or_create(pk=1)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("home_edit"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_non_owner_gets_403(self):
        self.client.force_login(self.regular)
        response = self.client.get(reverse("home_edit"))
        self.assertEqual(response.status_code, 403)

    def test_superuser_without_owner_role_gets_403(self):
        self.client.force_login(self.superuser_no_role)
        response = self.client.get(reverse("home_edit"))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_access(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("home_edit"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/home_edit.html")

    def test_post_saves_navbar_title(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("home_edit"),
            {
                "navbar_title_ru": "TestNavbar",
                "navbar_title_kk": "TestNavbarKK",
                "navbar_title_en": "Cycling",
                "page_title_ru": "TestTitle",
                "page_title_kk": "TestTitleKK",
                "page_title_en": "Home",
                "body_ru": "<p>Hello</p>",
                "body_kk": "",
                "body_en": "",
            },
        )
        sc = SiteContent.objects.get(pk=1)
        self.assertEqual(sc.navbar_title_ru, "TestNavbar")
        self.assertEqual(sc.navbar_title_en, "Cycling")
        self.assertEqual(sc.body_ru, "<p>Hello</p>")

    def test_post_redirects_to_home_on_success(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("home_edit"),
            {
                "navbar_title_ru": "X",
                "navbar_title_kk": "",
                "navbar_title_en": "",
                "page_title_ru": "",
                "page_title_kk": "",
                "page_title_en": "",
                "body_ru": "",
                "body_kk": "",
                "body_en": "",
            },
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)


class HomePageContextTests(WagtailPageTestCase):
    def setUp(self):
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite3", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)
        self.sc = SiteContent.objects.get_or_create(pk=1, defaults={"navbar_title_ru": "TestNavbar"})[0]

    def test_home_page_context_has_site_content(self):
        response = self.client.get(self.homepage.url)
        self.assertIn("site_content", response.context)

    def test_home_page_shows_body_when_set(self):
        self.sc.body_ru = "<p>Site content</p>"
        self.sc.save()
        response = self.client.get(self.homepage.url)
        self.assertContains(response, "Site content")


class LangDisplayCodeFilterTest(TestCase):
    def setUp(self):
        from home.templatetags.home_tags import lang_display_code

        self.f = lang_display_code

    def test_kk_maps_to_kz(self):
        self.assertEqual(self.f("kk"), "KZ")

    def test_ru_maps_to_ru(self):
        self.assertEqual(self.f("ru"), "RU")

    def test_en_maps_to_en(self):
        self.assertEqual(self.f("en"), "EN")

    def test_regional_subtag_stripped(self):
        self.assertEqual(self.f("en-us"), "EN")

    def test_none_returns_empty(self):
        self.assertEqual(self.f(None), "")

    def test_empty_string_returns_empty(self):
        self.assertEqual(self.f(""), "")

    def test_unknown_code_uppercased(self):
        self.assertEqual(self.f("fr"), "FR")
