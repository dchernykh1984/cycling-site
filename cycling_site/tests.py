from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase

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
