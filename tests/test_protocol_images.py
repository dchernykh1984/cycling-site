"""What a protocol is allowed to load, and from where.

A protocol is a file an organizer uploads and we show on our own domain, so it is framed with
`sandbox` under a policy that forbids it to reach outside. Forbidding everything outside also
forbade the organizer's own logo -- uploaded to this very site, served from this very domain, and
still blocked, because the policy named no address at all.
"""

import datetime
import re
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from calendar_app.models import Competition
from protocols.models import Protocol

HTML = b"<html><body><h1>Results</h1></body></html>"


def _directive(policy, name):
    """One directive of a Content-Security-Policy header, as the browser reads it."""
    for part in policy.split(";"):
        tokens = part.split()
        if tokens and tokens[0] == name:
            return tokens[1:]
    return None


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProtocolImagePolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title_ru="Race with a logo",
            date_start=datetime.date.today(),
            status=Competition.Status.APPROVED,
        )

    def setUp(self):
        self.protocol = Protocol.objects.create(
            competition=self.competition, protocol_type="absolute", is_live=False, file_hash="abc"
        )
        self.protocol.html_file.save("p.html", ContentFile(HTML), save=True)

    def _policy(self, **extra):
        response = self.client.get(f"/ru/protocols/{self.protocol.pk}/html/", **extra)
        self.assertEqual(response.status_code, 200)
        return response["Content-Security-Policy"]

    def test_a_protocol_may_show_an_image_from_the_site_it_is_served_by(self):
        self.assertIn("http://testserver", _directive(self._policy(), "img-src"))

    def test_the_address_follows_the_deployment_rather_than_being_written_down(self):
        """The same code runs on production, on staging and on a laptop; each allows its own host."""
        with override_settings(ALLOWED_HOSTS=["staging.example.org"]):
            policy = self._policy(HTTP_HOST="staging.example.org")
        self.assertIn("http://staging.example.org", _directive(policy, "img-src"))
        self.assertNotIn("http://testserver", _directive(policy, "img-src"))

    def test_media_kept_on_another_host_is_allowed_too(self):
        """A bucket or a CDN is a different origin from the site's own."""
        with override_settings(MEDIA_URL="https://cdn.example.net/media/"):
            sources = _directive(self._policy(), "img-src")
        self.assertIn("https://cdn.example.net", sources)
        self.assertIn("http://testserver", sources)

    def test_an_inline_image_still_works(self):
        self.assertIn("data:", _directive(self._policy(), "img-src"))

    def test_no_other_site_may_be_reached(self):
        """The point of the sandbox: a file someone else wrote must not call home."""
        sources = _directive(self._policy(), "img-src")
        self.assertNotIn("*", sources)
        self.assertNotIn("https:", sources)
        for source in sources:
            self.assertIn(source, ("data:", "http://testserver"))

    def test_everything_else_stays_forbidden(self):
        policy = self._policy()
        self.assertEqual(_directive(policy, "default-src"), ["'none'"])
        for directive in ("connect-src", "object-src", "frame-src", "base-uri", "form-action"):
            self.assertEqual(_directive(policy, directive), ["'none'"], directive)
        self.assertEqual(_directive(policy, "sandbox"), ["allow-scripts"])

    def test_the_document_cannot_be_told_apart_from_the_site_by_the_policy_alone(self):
        """`'self'` would be the obvious spelling and is useless here: the frame is sandboxed
        without allow-same-origin, so the protocol's origin is opaque and matches nothing."""
        self.assertNotIn("'self'", _directive(self._policy(), "img-src"))

    def test_the_header_is_one_line_a_browser_can_parse(self):
        policy = self._policy()
        self.assertNotIn("\n", policy)
        self.assertIsNone(re.search(r";\s*;", policy))
