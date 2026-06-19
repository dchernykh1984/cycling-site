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
from cycling_site.sanitize import plaintext_to_html, sanitize_rich_html


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


class MediaServingTests(TestCase):
    """User-uploaded media must be served by the app in production too: CodeRed forwards
    /media/ to the app and Django only auto-serves media under DEBUG, so without an explicit
    route the Wagtail catch-all turns every /media/ hit into a 404 (works locally, 404s in prod)."""

    def test_media_file_is_served_when_not_debug(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        hero_dir = Path(tmp) / "news" / "hero"
        hero_dir.mkdir(parents=True)
        payload = b"\xff\xd8\xff\xe0\x00\x10JFIF fake image bytes"
        (hero_dir / "logo.jpg").write_bytes(payload)
        with override_settings(DEBUG=False, MEDIA_ROOT=tmp):
            resp = self.client.get("/media/news/hero/logo.jpg")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), payload)

    def test_missing_media_returns_404_not_500(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with override_settings(DEBUG=False, MEDIA_ROOT=tmp):
            resp = self.client.get("/media/news/hero/missing.jpg")
        self.assertEqual(resp.status_code, 404)


class SanitizeRichHtmlTests(SimpleTestCase):
    def test_strips_script_keeps_formatting(self):
        out = sanitize_rich_html("<p>Hi <strong>bold</strong></p><script>alert(1)</script>")
        self.assertIn("<strong>bold</strong>", out)
        self.assertNotIn("<script", out)

    def test_link_opens_in_new_tab(self):
        out = sanitize_rich_html('<a href="https://x.com">x</a>')
        self.assertIn('href="https://x.com"', out)
        self.assertIn('target="_blank"', out)
        self.assertIn('rel="noopener"', out)

    def test_javascript_href_dropped(self):
        out = sanitize_rich_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn("javascript:", out)

    def test_img_stripped_by_default(self):
        out = sanitize_rich_html('<p>a<img src="https://x.com/i.png">b</p>')
        self.assertNotIn("<img", out)

    def test_img_kept_when_allowed_attrs_filtered(self):
        out = sanitize_rich_html('<img src="https://x.com/i.png" alt="t" onerror="hack()">', allow_img=True)
        self.assertIn("<img", out)
        self.assertIn('src="https://x.com/i.png"', out)
        self.assertIn('alt="t"', out)
        self.assertNotIn("onerror", out)

    def test_img_base64_raster_kept(self):
        out = sanitize_rich_html('<img src="data:image/png;base64,AAAA">', allow_img=True)
        self.assertIn("<img", out)

    def test_img_svg_and_js_data_dropped(self):
        self.assertNotIn("<img", sanitize_rich_html('<img src="data:image/svg+xml;base64,AAAA">', allow_img=True))
        self.assertNotIn("<img", sanitize_rich_html('<img src="javascript:alert(1)">', allow_img=True))

    def test_plaintext_to_html_escapes_and_linkifies(self):
        out = plaintext_to_html("See https://almaty-marathon.kz/ru/events\n\n<b>x</b> & y")
        self.assertIn(
            '<a target="_blank" rel="noopener noreferrer nofollow" href="https://almaty-marathon.kz/ru/events"',
            out,
        )
        self.assertIn("&lt;b&gt;", out)  # HTML escaped, not interpreted
        self.assertIn("&amp;", out)
        self.assertIn("<p>", out)
