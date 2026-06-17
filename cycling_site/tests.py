import logging
import shutil
import tempfile
from pathlib import Path

from django.core import mail
from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import translation

from cycling_site.logconfig import build_logging_config
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


class LoggingConfigTests(SimpleTestCase):
    def test_file_handler_writes_under_given_log_dir(self):
        # Logs must live under BASE_DIR (=/www in prod) so they are reachable via `cr download`.
        cfg = build_logging_config(Path("/www/logs"))
        self.assertEqual(cfg["handlers"]["file"]["filename"], "/www/logs/django.log")

    def test_request_errors_are_wired_to_admin_email_handler(self):
        cfg = build_logging_config(Path("/www/logs"))
        self.assertIn("mail_admins", cfg["loggers"]["django.request"]["handlers"])
        mail_admins = cfg["handlers"]["mail_admins"]
        self.assertEqual(mail_admins["class"], "django.utils.log.AdminEmailHandler")
        self.assertIn("require_debug_false", mail_admins["filters"])

    def _log_a_request_error(self):
        request = RequestFactory().get("/boom")
        logger = logging.getLogger("django.request")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.error(
                "Internal Server Error: /boom",
                exc_info=True,
                extra={"status_code": 500, "request": request},
            )

    def test_500_emails_admins_when_not_debug(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cfg = build_logging_config(Path(tmp))
        with override_settings(
            LOGGING=cfg,
            DEBUG=False,
            ADMINS=["ops@example.com"],
            SERVER_EMAIL="server@example.com",
        ):
            self._log_a_request_error()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ops@example.com"])
        self.assertEqual(mail.outbox[0].from_email, "server@example.com")
        self.assertIn("Internal Server Error", mail.outbox[0].subject)

    def test_no_admin_email_when_debug(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cfg = build_logging_config(Path(tmp))
        with override_settings(
            LOGGING=cfg,
            DEBUG=True,
            ADMINS=["ops@example.com"],
            SERVER_EMAIL="server@example.com",
        ):
            self._log_a_request_error()
        self.assertEqual(len(mail.outbox), 0)
