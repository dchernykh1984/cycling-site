from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import translation

from cycling_site.middleware import LocaleFallbackMiddleware


class LocaleFallbackMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = lambda request: HttpResponse("ok")
        self.middleware = LocaleFallbackMiddleware(self.get_response)

    def test_non_404_exception_is_not_handled(self):
        request = self.factory.get("/some/path/")
        result = self.middleware.process_exception(request, ValueError("boom"))
        self.assertIsNone(result)

    def test_http404_returns_404_response_with_custom_template(self):
        request = self.factory.get("/bulbul/")
        response = self.middleware.process_exception(request, Http404())
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 404)

    def test_http404_renders_404_template(self):
        request = self.factory.get("/bulbul/")
        response = self.middleware.process_exception(request, Http404())
        self.assertIn(b"404", response.content)

    def test_http404_in_default_locale_returns_404(self):
        # A missing Wagtail page in the default locale must NOT be silently
        # swapped for a foreign-locale article; return custom 404 instead.
        request = self.factory.get("/knowledge/some-article/")
        with translation.override("ru"):
            response = self.middleware.process_exception(request, Http404())
        self.assertEqual(response.status_code, 404)

    def test_http404_in_non_default_locale_returns_404(self):
        # Locale fallback has been intentionally removed; a page that does not
        # exist in the active locale returns 404, not the default-locale page.
        request = self.factory.get("/knowledge/some-article/")
        with translation.override("kk"):
            response = self.middleware.process_exception(request, Http404())
        self.assertEqual(response.status_code, 404)


class Custom404IntegrationTests(TestCase):
    """Custom 404.html is served even with DEBUG=True (no Django debug page)."""

    def test_nonexistent_url_returns_404(self):
        response = self.client.get("/bulbul/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_url_uses_custom_404_template(self):
        response = self.client.get("/bulbul/")
        self.assertTemplateUsed(response, "404.html")

    def test_nonexistent_url_in_kazakh_locale_returns_404(self):
        response = self.client.get("/bulbul/", HTTP_ACCEPT_LANGUAGE="kk")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
