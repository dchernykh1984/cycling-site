"""Reading protocols through the API: what the protocol pages show, under the rule they use."""

import json
import shutil
import tempfile
import uuid

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from accounts.models import User
from calendar_app.models import Competition, CompetitionInvite
from protocols import sections
from protocols.models import Protocol

UPLOAD = "/api/v1/protocols/upload/"
LIST = "/api/v1/protocols/?competition_id={}"
DETAIL = "/api/v1/protocols/{}"
HTML = "/api/v1/protocols/{}/html"
PAGE = "/en/protocols/{}/"

# The page strips a script that loads from elsewhere; the API gives the file exactly as it came.
HTML_FILE = (
    b'<html><body><table><tr><td>8,4</td></tr></table><script src="https://example.com/x.js"></script></body></html>'
)
DOCUMENT = {
    "schema": 1,
    "sections": [
        {
            "columns": [{"id": "bib", "role": "bib"}, {"id": "run", "label": "60 m"}, {"id": "jump", "label": "Jump"}],
            "rows": [{"cells": {"bib": "7", "run": "8,4", "jump": "2,35"}}],
        }
    ],
}
ALL_ROUND = {"ru": "All-round (ru)", "kk": "All-round (kk)", "en": "All-round"}


def _member(username: str, role=User.Role.PARTICIPANT) -> User:
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password="Pass1234!", role=role)
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return user


def _bearer(user: User | None) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {user.api_token}"} if user else {}


class ProtocolReadApiTest(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        settings_override = override_settings(MEDIA_ROOT=media)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.author = _member("author", User.Role.ORGANIZER)
        self.race = Competition.objects.create(
            title_ru="Race", date_start="2027-05-30", status=Competition.Status.APPROVED, submitted_by=self.author
        )
        sections.add(self.race, ALL_ROUND)
        self.absolute = self._upload(html=HTML_FILE, document=DOCUMENT)
        self.all_round = self._upload(html=b"<html><body>group</body></html>", protocol_type="group", section=2)

    def _upload(self, *, html: bytes | None = None, document: dict | None = None, **fields) -> Protocol:
        data = {"competition_token": str(self.race.upload_token), "protocol_type": "absolute", **fields}
        if html is not None:
            data["html_file"] = SimpleUploadedFile("protocol.html", html, content_type="text/html")
        if document is not None:
            raw = json.dumps(document).encode()
            data["document"] = SimpleUploadedFile("protocol.json", raw, content_type="application/json")
        with self.captureOnCommitCallbacks(execute=True):
            answer = Client().post(UPLOAD, data)
        self.assertEqual(answer.status_code, 200, answer.content)
        return Protocol.objects.get(pk=answer.json()["id"])

    def _get(self, url: str, user: User | None = None):
        return self.client.get(url, **_bearer(user))

    def test_anybody_lists_a_published_events_protocols_in_the_order_of_its_sections(self):
        answer = self._get(LIST.format(self.race.pk))
        self.assertEqual(answer.status_code, 200)
        first, second = answer.json()
        self.assertEqual((first["id"], first["section"], first["protocol_type"]), (self.absolute.pk, 1, "absolute"))
        self.assertEqual(first["section_name"], sections.names(None))
        self.assertEqual((first["shown"], first["has_html"], first["is_live"]), ("document", True, True))
        self.assertEqual(first["file_hash"], self.absolute.file_hash)
        self.assertEqual((second["id"], second["section"], second["section_name"]), (self.all_round.pk, 2, ALL_ROUND))
        self.assertEqual(second["shown"], "html")

    def test_an_event_without_protocols_lists_none(self):
        quiet = Competition.objects.create(
            title_ru="Quiet", date_start="2027-06-01", status=Competition.Status.APPROVED
        )
        self.assertEqual(self._get(LIST.format(quiet.pk)).json(), [])

    def test_a_protocol_gives_its_document_and_its_update_history_the_latest_first(self):
        again = self._upload(html=HTML_FILE, document={**DOCUMENT, "lang": "en"})
        answer = self._get(DETAIL.format(again.pk)).json()
        self.assertEqual(answer["document"], again.document)  # as the site keeps it: defaults filled in
        self.assertEqual(answer["document"]["lang"], "en")
        self.assertEqual(
            answer["document"]["sections"][0]["rows"][0]["cells"], {"bib": "7", "run": "8,4", "jump": "2,35"}
        )
        self.assertEqual([version["file_hash"] for version in answer["versions"]][:1], [again.file_hash])
        self.assertEqual(len(answer["versions"]), 2)
        self.assertGreaterEqual(answer["versions"][0]["saved_at"], answer["versions"][1]["saved_at"])

    def test_two_uploads_saved_in_the_same_instant_come_the_later_first(self):
        again = self._upload(html=HTML_FILE)
        again.versions.update(saved_at=again.versions.first().saved_at)
        hashes = [version["file_hash"] for version in self._get(DETAIL.format(again.pk)).json()["versions"]]
        self.assertEqual(hashes, list(again.versions.order_by("-pk").values_list("file_hash", flat=True)))

    def test_html_alone_gives_no_document(self):
        answer = self._get(DETAIL.format(self.all_round.pk)).json()
        self.assertIsNone(answer["document"])
        self.assertEqual(answer["shown"], "html")

    def test_the_html_file_comes_as_it_was_uploaded_under_the_pages_policy(self):
        answer = self._get(HTML.format(self.absolute.pk))
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.content, HTML_FILE)
        self.assertEqual(answer["Content-Type"], "text/html; charset=utf-8")
        policy = answer["Content-Security-Policy"]
        self.assertIn("default-src 'none'", policy)
        self.assertIn("sandbox allow-scripts", policy)
        self.assertEqual(answer["X-Content-Type-Options"], "nosniff")
        self.assertTrue(answer["Content-Disposition"].startswith("attachment"))

    def test_a_protocol_without_an_html_file_has_none_to_give(self):
        drawn = self._upload(document=DOCUMENT, protocol_type="group")
        self.assertFalse(self._get(DETAIL.format(drawn.pk)).json()["has_html"])
        self.assertEqual(self._get(HTML.format(drawn.pk)).status_code, 404)

    def test_a_file_gone_from_the_storage_is_a_404(self):
        default_storage.delete(self.absolute.html_file.name)
        self.assertEqual(self._get(HTML.format(self.absolute.pk)).status_code, 404)

    def test_an_event_nobody_may_read_answers_as_one_that_does_not_exist(self):
        """Unpublished, hidden or deleted: 404 for everybody, its managers too, as on the protocol pages."""
        admin = _member("admin", User.Role.ADMIN)
        changes = {
            "unpublished": {"status": Competition.Status.PENDING_APPROVAL},
            "hidden": {"is_hidden": True},
            "deleted": {"is_deleted": True},
        }
        for label, change in changes.items():
            published = {"status": Competition.Status.APPROVED, "is_hidden": False, "is_deleted": False}
            Competition.objects.filter(pk=self.race.pk).update(**{**published, **change})
            for user in (None, admin, self.author):
                with self.subTest(event=label, user=user and user.username):
                    for url in (
                        LIST.format(self.race.pk),
                        DETAIL.format(self.absolute.pk),
                        HTML.format(self.absolute.pk),
                    ):
                        self.assertEqual(self._get(url, user).status_code, 404)
        # Beyond the database's integers too: a 404 like any other id, never a failed query.
        for number in (10**9, 10**20):
            for missing in (LIST.format(number), DETAIL.format(number), HTML.format(number)):
                self.assertEqual(self._get(missing).status_code, 404)

    def test_an_invite_only_events_protocols_are_for_those_it_lets_in(self):
        Competition.objects.filter(pk=self.race.pk).update(invite_only=True)
        invited, stranger = _member("invited"), _member("stranger")
        CompetitionInvite.objects.create(competition=self.race, user=invited)
        admin = _member("admin", User.Role.ADMIN)
        expected = {None: 404, stranger: 404, invited: 200, self.author: 200, admin: 200}
        for user, status in expected.items():
            with self.subTest(user=user and user.username):
                for url in (LIST.format(self.race.pk), DETAIL.format(self.absolute.pk), HTML.format(self.absolute.pk)):
                    self.assertEqual(self._get(url, user).status_code, status)

    def test_the_api_and_the_protocol_page_let_in_the_same_readers(self):
        stranger, invited, admin = _member("stranger"), _member("invited"), _member("admin", User.Role.ADMIN)
        CompetitionInvite.objects.create(competition=self.race, user=invited)
        states = {
            "published": {},
            "invite-only": {"invite_only": True},
            "hidden": {"is_hidden": True},
            "unpublished": {"status": Competition.Status.PENDING_APPROVAL},
            "deleted": {"is_deleted": True},
        }
        published = {
            "status": Competition.Status.APPROVED,
            "is_hidden": False,
            "is_deleted": False,
            "invite_only": False,
        }
        for label, change in states.items():
            Competition.objects.filter(pk=self.race.pk).update(**{**published, **change})
            for user in (None, stranger, invited, self.author, admin):
                with self.subTest(event=label, user=user and user.username):
                    browser = Client()
                    if user is not None:
                        browser.force_login(user)
                    page = browser.get(PAGE.format(self.absolute.pk)).status_code
                    self.assertEqual(self._get(DETAIL.format(self.absolute.pk), user).status_code, page)

    def test_a_token_nobody_holds_is_refused(self):
        answer = self.client.get(LIST.format(self.race.pk), HTTP_AUTHORIZATION=f"Bearer {uuid.uuid4()}")
        self.assertEqual(answer.status_code, 401)

    def test_the_upload_address_still_takes_no_get(self):
        self.assertEqual(self.client.get(UPLOAD).status_code, 405)
