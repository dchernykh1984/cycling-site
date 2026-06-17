import importlib
import io
import shutil
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage
from wagtail.images import get_image_model
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
        # Page.locale uses on_delete=PROTECT; delete locale-specific pages first.
        for locale in Locale.objects.filter(language_code__in=["kk", "en"]):
            Page.objects.filter(locale=locale).delete()
        Locale.objects.filter(language_code__in=["kk", "en"]).delete()

        migration_mod.create_locales(django_apps, None)

        self.assertTrue(Locale.objects.filter(language_code="ru").exists())
        self.assertFalse(Locale.objects.filter(language_code="en-us").exists())
        self.assertTrue(Locale.objects.filter(language_code="kk").exists())
        self.assertTrue(Locale.objects.filter(language_code="en").exists())


class LocaleFallbackMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_middleware(self):
        from cycling_site.middleware import LocaleFallbackMiddleware

        return LocaleFallbackMiddleware(lambda r: HttpResponse(status=200))

    def test_anonymous_user_passes_through(self):
        from django.contrib.auth.models import AnonymousUser

        mw = self._make_middleware()
        request = self.factory.get("/")
        request.user = AnonymousUser()
        response = mw(request)
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_preferred_language_activated(self):
        user = User.objects.create_user(
            username="mw_test", email="mw@test.com", password="pass", preferred_language="kk"
        )
        mw = self._make_middleware()
        request = self.factory.get("/")
        request.user = user
        mw(request)
        self.assertEqual(request.LANGUAGE_CODE, "kk")

    def test_authenticated_user_no_preferred_language_passes_through(self):
        user = User.objects.create_user(
            username="mw_test2", email="mw2@test.com", password="pass", preferred_language=""
        )
        mw = self._make_middleware()
        request = self.factory.get("/")
        request.user = user
        response = mw(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(hasattr(request, "LANGUAGE_CODE"))

    def test_request_without_user_passes_through(self):
        mw = self._make_middleware()
        request = self.factory.get("/")
        response = mw(request)
        self.assertEqual(response.status_code, 200)


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
        self.homepage = HomePage(title="Home", slug="home-ctx")
        root_page.add_child(instance=self.homepage)
        # Route this homepage at "/" via a clean default site so the tests don't depend on
        # the slug a sibling test may have already taken ("home" -> "home-2") on the worker.
        Site.objects.all().delete()
        Site.objects.create(hostname="testserver", root_page=self.homepage, is_default_site=True)
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


class AdminUploadAndEditScenarioTests(TestCase):
    """Regression for the production 500s reported on 2026-06-17: adding an image via the
    Wagtail admin (multiple-image upload) and opening a page for editing. Both flows must
    work end to end (they pass locally; the prod failure is environment-specific)."""

    def setUp(self):
        self._media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        self.admin = User.objects.create_user(
            username="wagtail_admin",
            email="wagtail_admin@example.com",
            password="Pass1234!",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    @staticmethod
    def _png(name="logo.png", mode="RGB", color=(255, 128, 0)):
        buf = io.BytesIO()
        PILImage.new(mode, (40, 40), color).save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def test_multiple_image_upload_creates_image_and_rendition(self):
        image_model = get_image_model()
        with override_settings(MEDIA_ROOT=self._media):
            resp = self.client.post("/admin/images/multiple/add/", {"files[]": self._png()})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            image = image_model.objects.get(pk=data["image_id"])
            # Generating a rendition exercises the media write/read path the admin relies on.
            self.assertTrue(image.get_rendition("max-100x100").url)

    def test_rgba_png_upload_succeeds(self):
        with override_settings(MEDIA_ROOT=self._media):
            resp = self.client.post(
                "/admin/images/multiple/add/",
                {"files[]": self._png(name="rgba.png", mode="RGBA", color=(0, 128, 255, 128))},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_homepage_edit_view_renders(self):
        home = HomePage.objects.first()
        if home is None:
            root = Page.objects.get(depth=1)
            home = HomePage(title="Home", slug="home-edit-test")
            root.add_child(instance=home)
        resp = self.client.get(reverse("wagtailadmin_pages:edit", args=[home.id]))
        self.assertEqual(resp.status_code, 200)
