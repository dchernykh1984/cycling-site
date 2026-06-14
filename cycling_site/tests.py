from unittest.mock import patch

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

    def test_404_in_default_locale_is_not_handled(self):
        request = self.factory.get("/some/path/")
        with translation.override("ru"):
            result = self.middleware.process_exception(request, Http404())
        self.assertIsNone(result)

    def test_404_in_non_default_locale_retries_with_default_locale(self):
        request = self.factory.get("/knowledge/article/")
        fallback_response = HttpResponse("fallback content")

        with translation.override("kk"):
            with patch("wagtail.views.serve", return_value=fallback_response) as mock_serve:
                result = self.middleware.process_exception(request, Http404())

        mock_serve.assert_called_once()
        self.assertIs(result, fallback_response)

    def test_fallback_restores_original_language(self):
        request = self.factory.get("/knowledge/article/")
        fallback_response = HttpResponse("fallback content")

        with translation.override("kk"):
            with patch("wagtail.views.serve", return_value=fallback_response):
                self.middleware.process_exception(request, Http404())
            self.assertEqual(translation.get_language(), "kk")

    def test_404_in_non_default_locale_with_no_wagtail_page_returns_none(self):
        request = self.factory.get("/truly/nonexistent/")

        with translation.override("kk"):
            with patch("wagtail.views.serve", side_effect=Http404()):
                result = self.middleware.process_exception(request, Http404())

        self.assertIsNone(result)

    def test_fallback_restores_original_language_even_when_wagtail_also_404s(self):
        request = self.factory.get("/truly/nonexistent/")

        with translation.override("kk"):
            with patch("wagtail.views.serve", side_effect=Http404()):
                self.middleware.process_exception(request, Http404())
            self.assertEqual(translation.get_language(), "kk")
