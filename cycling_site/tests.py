import http.client
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.core import mail
from django.db import connection
from django.http import Http404, HttpResponse
from django.test import LiveServerTestCase, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import translation

from cycling_site.logconfig import build_logging_config
from cycling_site.middleware import LocaleFallbackMiddleware
from cycling_site.sanitize import sanitize_rich_html


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
        request = self.factory.get("/ru/knowledge/some-article/")
        with translation.override("ru"):
            response = self.middleware.process_exception(request, Http404())
        self.assertEqual(response.status_code, 404)

    def test_http404_in_non_default_locale_returns_404(self):
        # Locale fallback has been intentionally removed; a page that does not
        # exist in the active locale returns 404, not the default-locale page.
        request = self.factory.get("/ru/knowledge/some-article/")
        with translation.override("kk"):
            response = self.middleware.process_exception(request, Http404())
        self.assertEqual(response.status_code, 404)


class Custom404IntegrationTests(TestCase):
    """Custom 404.html is served even with DEBUG=True (no Django debug page)."""

    def test_nonexistent_url_returns_404(self):
        response = self.client.get("/ru/bulbul/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_url_uses_custom_404_template(self):
        response = self.client.get("/ru/bulbul/")
        self.assertTemplateUsed(response, "404.html")

    def test_nonexistent_url_in_kazakh_locale_returns_404(self):
        response = self.client.get("/kk/bulbul/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

    def test_an_address_without_a_language_is_sent_to_one(self):
        """Reader-facing addresses live under /ru/, /kk/ and /en/; the bare path redirects to
        whichever of them the reader asked for, and only then answers."""
        response = self.client.get("/bulbul/", HTTP_ACCEPT_LANGUAGE="kk")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/kk/bulbul/")


class LoggingConfigTests(SimpleTestCase):
    def test_production_smtp_has_a_finite_overridable_timeout(self):
        script = """
import importlib
import os
import sys
os.environ.update(SECRET_KEY='test', DATABASE_URL='postgres://localhost/test', LOG_DIR=sys.argv[1])
os.environ['PRIMARY_HOST'] = 'example.com'
os.environ.pop('EMAIL_TIMEOUT', None)
from cycling_site.settings import prod
assert prod.EMAIL_TIMEOUT == 5
os.environ['EMAIL_TIMEOUT'] = '2.5'
assert importlib.reload(prod).EMAIL_TIMEOUT == 2.5
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(  # noqa: S603 -- fixed script and current interpreter
                [sys.executable, "-c", script, directory], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_will_not_start_without_its_own_host(self):
        script = """
import os
import sys
os.environ.update(SECRET_KEY='test', DATABASE_URL='postgres://localhost/test', LOG_DIR=sys.argv[1])
for name in ('PRIMARY_HOST', 'VIRTUAL_HOST'):
    os.environ.pop(name, None)
from cycling_site.settings import prod
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(  # noqa: S603 -- fixed script and current interpreter
                [sys.executable, "-c", script, directory], capture_output=True, text=True, timeout=15
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set PRIMARY_HOST (or VIRTUAL_HOST)", result.stderr)

    def test_worker_timeouts_email_admins_without_an_http_request(self):
        # Configure logging in a child so the test cannot replace pytest's own handlers.
        script = """
import logging
from pathlib import Path
import sys
from django.conf import settings
from cycling_site.logconfig import build_logging_config
settings.configure(
    DEBUG=False, SECRET_KEY='test', ADMINS=['ops@example.com'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    LOGGING=build_logging_config(Path(sys.argv[1])),
)
import django
django.setup()
from django.core import mail
mail.get_connection()
http = logging.getLogger('django.request')
http.error('Preview temporarily unavailable', extra={'status_code': 503})
assert len(mail.outbox) == 0
http.error('Internal Server Error', extra={'status_code': 500})
assert len(mail.outbox) == 1
mail.outbox.clear()
try:
    raise ValueError('Unexpected storage failure')
except ValueError:
    http.exception('Unexpected service error', extra={'status_code': 503})
assert len(mail.outbox) == 1
mail.outbox.clear()
logger = logging.getLogger('gunicorn.error')
logger.error('WORKER TIMEOUT (pid:123)')
assert len(mail.outbox) == 1
assert 'WORKER TIMEOUT' in mail.outbox[0].subject
assert mail.outbox[0].to == ['ops@example.com']
logger.warning('Worker is restarting')
assert len(mail.outbox) == 1
settings.DEBUG = True
logger.error('WORKER TIMEOUT (pid:456)')
assert len(mail.outbox) == 1
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(  # noqa: S603 -- fixed script and current interpreter
                [sys.executable, "-c", script, directory], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_a_protocol_file_is_never_served_as_a_page_of_the_site(self):
        """A protocol is HTML somebody else wrote: its own views frame it in a sandbox, and /media/ must
        not hand the file out as a page of the site, by any spelling of its address."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for folder, name in (("protocols", "abs.html"), ("protocol_versions", "v_abs.html")):
            (Path(tmp) / folder).mkdir()
            (Path(tmp) / folder / name).write_text("<script>document.title = 'ours'</script>")
        addresses = (
            "/media/protocols/abs.html",
            "/media/protocol_versions/v_abs.html",
            "/media/news/../protocols/abs.html",
            "/media/./protocols/abs.html",
            "/media/Protocols/abs.html",
        )
        with override_settings(DEBUG=False, MEDIA_ROOT=tmp):
            for address in addresses:
                with self.subTest(address=address):
                    self.assertEqual(self.client.get(address).status_code, 404)

    def test_an_upload_cannot_act_as_a_page_of_the_site(self):
        """Opened directly, any upload but a PDF runs in a sandbox, and HTML or XML is downloaded rather
        than shown; images, SVG and PDFs still open in the browser."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        files = {
            "documents/page.html": b"<script>document.title = 'ours'</script>",
            "documents/feed.xml": b"<?xml version='1.0'?><feed/>",
            "news/hero/logo.svg": b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>",
            "news/hero/logo.png": b"\x89PNG\r\n\x1a\n fake image bytes",
            "documents/rules.pdf": b"%PDF-1.4 fake",
        }
        for name, content in files.items():
            (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / name).write_bytes(content)
        expected = {  # (opened how, sandboxed)
            "documents/page.html": ("attachment", True),
            "documents/feed.xml": ("attachment", True),
            "news/hero/logo.svg": ("inline", True),
            "news/hero/logo.png": ("inline", True),
            "documents/rules.pdf": ("inline", False),
        }
        with override_settings(DEBUG=False, MEDIA_ROOT=tmp):
            for name, (opened, sandboxed) in expected.items():
                with self.subTest(name=name):
                    resp = self.client.get(f"/media/{name}")
                    self.assertEqual(resp.status_code, 200)
                    self.assertTrue(resp["Content-Disposition"].startswith(opened), resp["Content-Disposition"])
                    self.assertEqual(resp.get("Content-Security-Policy") == "sandbox", sandboxed)


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

    def test_href_scheme_bypass_via_entities_and_control_chars_dropped(self):
        # Browsers strip ASCII control/whitespace chars from a URL scheme, so these all
        # resolve to javascript: and must be dropped. &#x0a;/&#10; are newline/tab entities
        # (BeautifulSoup decodes them); \t/\x00 are literal control chars in the source.
        for raw in (
            '<a href="java&#x0a;script:alert(1)">x</a>',
            '<a href="java&#10;script:alert(1)">x</a>',
            '<a href="javascript&#58;alert(1)">x</a>',
            '<a href="java\tscript:alert(1)">x</a>',
            '<a href="\x00javascript:alert(1)">x</a>',
            '<a href="  JAVASCRIPT:alert(1)">x</a>',
            '<a href="vb\tscript:msgbox(1)">x</a>',
        ):
            out = sanitize_rich_html(raw)
            self.assertNotIn("javascript", out.lower(), raw)
            self.assertNotIn("vbscript", out.lower(), raw)
            self.assertNotIn("href=", out, raw)

    def test_safe_schemes_and_relative_links_kept(self):
        for href in (
            "https://x.com",
            "http://x.com",
            "/ru/calendar/1/",
            "#section",
            "?q=1",
            "mailto:a@b.com",
            "tel:+123",
        ):
            out = sanitize_rich_html(f'<a href="{href}">x</a>')
            self.assertIn(f'href="{href}"', out, href)

    def test_a_link_to_another_page_opens_in_a_new_tab_and_one_to_a_part_of_this_page_stays(self):
        for href in ("https://x.com", "/ru/calendar/1/", "?q=1", "mailto:a@b.com"):
            out = sanitize_rich_html(f'<a href="{href}">x</a>')
            self.assertIn('target="_blank"', out, href)
            self.assertIn('rel="noopener"', out, href)
        # a target the author wrote is dropped as well: the page decides
        out = sanitize_rich_html('<a href="#section-2" target="_blank" rel="opener">x</a>')
        self.assertEqual(out, '<a href="#section-2">x</a>')

    def test_a_comment_or_cdata_a_browser_ends_at_its_first_gt_brings_no_handler_through(self):
        # html.parser read each of these as one comment or CDATA, written back as it came; a browser ends it at the
        # first ">" and runs the handler behind it. Which of them html.parser reads whole depends on the Python.
        for raw in (
            '<!--><img src=x onerror="alert(1)">-->',
            '<!---><img src=x onerror="alert(1)">-->',
            '<![CDATA[><img src=x onerror="alert(1)">]]>',
            '<p>ok</p><![CDATA[><a href="https://x.com" onmouseover="alert(1)">t</a>]]>',
        ):
            for allow_img in (False, True):
                with self.subTest(raw=raw, allow_img=allow_img):
                    out = sanitize_rich_html(raw, allow_img=allow_img)
                    self.assertNotIn("onerror", out)
                    self.assertNotIn("onmouseover", out)

    def test_data_href_dropped_on_anchor(self):
        out = sanitize_rich_html('<a href="data:text/html,<script>alert(1)</script>">x</a>')
        self.assertNotIn("href=", out)

    def test_underline_and_strike_kept(self):
        # The Quill toolbar offers underline/strike, so <u>/<s> must survive sanitization.
        out = sanitize_rich_html("<p><u>under</u> <s>strike</s></p>")
        self.assertIn("<u>under</u>", out)
        self.assertIn("<s>strike</s>", out)

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

    def test_img_size_and_float_kept(self):
        # The image tool writes width/height attributes + inline float/margin/display and a
        # data-align keyword; all of that must survive so a resized, wrapped image renders.
        raw = (
            '<img src="data:image/png;base64,AAAA" width="120" height="80" data-align="left"'
            ' style="float: left; margin: 0px 1em 1em 0px; display: inline;">'
        )
        out = sanitize_rich_html(raw, allow_img=True)
        self.assertIn('width="120"', out)
        self.assertIn('height="80"', out)
        self.assertIn('data-align="left"', out)
        self.assertIn("float: left", out)
        self.assertIn("margin: 0px 1em 1em 0px", out)

    def test_img_style_with_url_or_expression_dropped(self):
        # A style value that carries url()/expression() (a fetch/script vector) drops the whole
        # style attribute, but the image itself (safe src) is kept.
        bad_styles = (
            "background: url(javascript:alert(1))",
            "width: expression(alert(1))",
            "float: left; behavior: url(x)",
        )
        for bad in bad_styles:
            out = sanitize_rich_html(f'<img src="data:image/png;base64,AAAA" style="{bad}">', allow_img=True)
            self.assertIn("<img", out, bad)
            self.assertNotIn("url(", out, bad)
            self.assertNotIn("expression", out, bad)

    def test_img_bad_dimension_and_align_dropped(self):
        out = sanitize_rich_html(
            '<img src="data:image/png;base64,AAAA" width="alert(1)" height="9e9px" data-align="evil">',
            allow_img=True,
        )
        self.assertIn("<img", out)
        self.assertNotIn("width=", out)
        self.assertNotIn("data-align", out)

    def test_img_position_style_dropped(self):
        # Only size/float properties are allowed on an image; layout-escaping ones are dropped.
        out = sanitize_rich_html(
            '<img src="data:image/png;base64,AAAA" style="width: 50%; position: fixed; top: 0;">',
            allow_img=True,
        )
        self.assertIn("width: 50%", out)
        self.assertNotIn("position", out)

    def test_span_text_color_kept_other_style_dropped(self):
        out = sanitize_rich_html(
            '<p><span style="color: rgb(230, 0, 0); position: fixed;">r</span>'
            '<span style="background-color: #ff0;">h</span></p>'
        )
        self.assertIn("color: rgb(230, 0, 0)", out)
        self.assertIn("background-color: #ff0", out)
        self.assertNotIn("position", out)

    def test_a_colour_of_a_long_run_of_spaces_is_refused_in_well_under_a_second(self):
        # A protocol's header lines are sanitised on every draw: 100 lines of 20 000 such spaces took 80 seconds while
        # the spaces could be read two ways. The bound is generous; a check gone quadratic still fails it.
        started = time.perf_counter()
        out = sanitize_rich_html('<span style="color: rgb(' + " " * 40000 + 'x)">a</span>')
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertNotIn("rgb", out)

    def test_a_line_of_deeply_nested_unknown_tags_is_cleaned_in_well_under_a_second(self):
        # Unwrapping walked everything under each tag again: 8000 nested divs took seconds, and a document's 100
        # header and footer lines of them minutes a draw. The bound is generous; a cleanup gone quadratic fails it.
        started = time.perf_counter()
        out = sanitize_rich_html("<div><x a=1>" * 4000 + "kept")
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(out, "kept")

    def test_a_line_of_many_comments_is_cleaned_in_well_under_a_second(self):
        # Each comment was found by walking its parent's children from the first: 100 000 characters took two seconds,
        # and a document's 100 header and footer lines of them more each draw. The bound is generous, as above.
        started = time.perf_counter()
        out = sanitize_rich_html("a<!---->" * 12500, allow_img=True)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(out, "a" * 12500)

    def test_a_line_of_many_images_without_a_safe_src_is_cleaned_in_well_under_two_seconds(self):
        # Each such image was found by walking its parent's children from the first: 200 000 characters took 13
        # seconds, and a description may hold a million. The bound is generous, as above.
        started = time.perf_counter()
        out = sanitize_rich_html("a<img>" * 33334, allow_img=True)
        self.assertLess(time.perf_counter() - started, 2.0)
        self.assertEqual(out, "a" * 33334)

    def test_a_line_of_tags_nested_too_deep_to_write_back_comes_back_as_its_escaped_text(self):
        # Writing tags back asks whether one has closed by comparing tags recursively: 600 nested ran out of stack,
        # a 500 on a description's save and a failed draw for a protocol header line.
        out = sanitize_rich_html("<b>" * 600 + "x&lt;y</b>" * 600, allow_img=True)
        self.assertEqual(out, "x&lt;y" * 600)

    def test_hidden_images_without_a_safe_src_do_not_stop_a_deep_line_from_coming_back(self):
        # A hidden image stays among its parent's children, so that comparison went deeper than with the image
        # removed: this line, written back before, ran out of stack. It holds no text, so none comes back.
        raw = "<b>" * 600 + "".join(
            ("<img>" if j % 2 else "") + "<br>" + ("" if j % 2 else "<br>") + "</b>" for j in range(600, 0, -1)
        )
        self.assertEqual(sanitize_rich_html(raw, allow_img=True), "")

    def test_align_and_indent_classes_kept_others_dropped(self):
        out = sanitize_rich_html('<p class="ql-align-center hacker">c</p><ol><li class="ql-indent-2">i</li></ol>')
        self.assertIn('class="ql-align-center"', out)
        self.assertIn('class="ql-indent-2"', out)
        self.assertNotIn("hacker", out)

    def test_style_on_block_tag_dropped(self):
        # Alignment is carried by a class, so an inline style on a block tag is never needed and
        # is stripped (a paragraph cannot smuggle arbitrary CSS).
        out = sanitize_rich_html('<p style="color: red" class="evil">t</p>')
        self.assertIn("<p>t</p>", out)
        self.assertNotIn("style", out)
        self.assertNotIn("evil", out)

    def test_subscript_superscript_kept(self):
        out = sanitize_rich_html("<p>x<sub>2</sub> y<sup>n</sup></p>")
        self.assertIn("<sub>2</sub>", out)
        self.assertIn("<sup>n</sup>", out)


class VendoredStaticAssetsTests(SimpleTestCase):
    def test_no_sourcemap_references_in_vendored_assets(self):
        # prod uses ManifestStaticFilesStorage, which resolves //# sourceMappingURL refs while
        # hashing and raises (500 on every page loading the asset + breaks collectstatic) when
        # the .map isn't collected. We don't vendor .map files, so vendored JS/CSS must not
        # reference one.
        from django.apps import apps

        offenders = []
        for app_label in ("calendar_app", "knowledge"):
            try:
                app_path = Path(apps.get_app_config(app_label).path)
            except LookupError:
                continue
            vendor = app_path / "static" / app_label / "vendor"
            for asset in vendor.rglob("*"):
                if asset.suffix in {".js", ".css"} and "sourceMappingURL" in asset.read_text(encoding="utf-8"):
                    offenders.append(str(asset.relative_to(app_path)))
        self.assertEqual(offenders, [], f"vendored assets reference uncollected sourcemaps: {offenders}")


class LiveServerDatabaseConnectionsTests(LiveServerTestCase):
    """The test server gives each browser connection a thread, and a browser keeps its connections open
    long after a page: a thread must not hold a database connection while it waits, or a run of browser
    tests runs the database out of them."""

    def connections_open(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            return cursor.fetchone()[0]

    def test_an_idle_browser_connection_holds_no_database_connection(self):
        before = self.connections_open()
        browser = http.client.HTTPConnection(self.server_thread.host, self.server_thread.port, timeout=10)
        self.addCleanup(browser.close)
        browser.request("GET", "/api/v1/disciplines/")  # reads the database
        response = browser.getresponse()
        response.read()
        self.assertEqual(response.status, 200)
        self.assertNotEqual(response.getheader("Connection"), "close")  # kept open, as a browser's is
        deadline = time.monotonic() + 3
        while self.connections_open() > before and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.connections_open(), before)
