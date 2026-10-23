"""Replacing a protocol is all or nothing: a failed upload changes nothing, and uploads of one event
take turns, so the protocol always holds exactly one upload's content."""

import shutil
import tempfile
import threading
from pathlib import Path
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings

from calendar_app.models import Competition
from protocols.models import Protocol, ProtocolVersion

URL = "/api/v1/protocols/upload/"


def _html(text: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("protocol.html", f"<html><body>{text}</body></html>".encode(), content_type="text/html")


def _stored_files(root: str) -> set[str]:
    return {str(path.relative_to(root)) for path in Path(root).rglob("*") if path.is_file()}


class _MediaMixin:
    def _use_temp_media(self):
        self.media_root = tempfile.mkdtemp()
        self._media = override_settings(MEDIA_ROOT=self.media_root)
        self._media.enable()
        self.addCleanup(self._media.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)


class ReplaceProtocolTest(_MediaMixin, TestCase):
    def setUp(self):
        self._use_temp_media()
        self.competition = Competition.objects.create(
            title_ru="Race", date_start="2026-01-01", status=Competition.Status.APPROVED
        )
        self.token = str(self.competition.upload_token)
        with self.captureOnCommitCallbacks(execute=True):
            self._post("first")
        self.protocol = Protocol.objects.get()
        self.first_file = self.protocol.html_file.name

    def _post(self, text: str, **extra):
        data = {"competition_token": self.token, "protocol_type": "absolute", "html_file": _html(text)}
        data.update(extra)
        return Client(raise_request_exception=False).post(URL, data)

    def _assert_first_upload_intact(self):
        protocol = Protocol.objects.get()
        self.assertEqual(protocol.html_file.name, self.first_file)
        self.assertTrue(default_storage.exists(self.first_file))
        with protocol.html_file.open("rb") as f:
            self.assertIn(b"first", f.read())
        self.assertEqual(ProtocolVersion.objects.count(), 1)

    def test_displaced_file_is_deleted_only_after_the_switch_commits(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.assertEqual(self._post("second").status_code, 200)
        self.assertTrue(default_storage.exists(self.first_file))
        for callback in callbacks:
            callback()
        self.assertFalse(default_storage.exists(self.first_file))
        self.assertTrue(Protocol.objects.get().html_file.name != self.first_file)

    def test_storage_failure_on_the_second_file_removes_the_first_and_keeps_the_protocol(self):
        real_save = default_storage.save
        saved = []

        def save(name, content, *args, **kwargs):
            if saved:
                raise OSError("disk full")
            saved.append(real_save(name, content, *args, **kwargs))
            return saved[-1]

        before = _stored_files(self.media_root)
        with mock.patch.object(default_storage, "save", side_effect=save):
            self.assertEqual(self._post("second").status_code, 500)
        self.assertEqual(_stored_files(self.media_root), before)
        self._assert_first_upload_intact()

    def test_database_failure_removes_the_new_files_and_keeps_the_protocol(self):
        before = _stored_files(self.media_root)
        with mock.patch.object(ProtocolVersion.objects, "create", side_effect=RuntimeError("db down")):
            self.assertEqual(self._post("second", is_live="false").status_code, 500)
        self.assertEqual(_stored_files(self.media_root), before)
        self._assert_first_upload_intact()
        self.assertTrue(Protocol.objects.get().is_live)

    def test_failing_to_delete_a_displaced_file_still_answers_200(self):
        with (
            mock.patch.object(default_storage, "delete", side_effect=OSError("busy")),
            self.assertLogs("api.endpoints.protocols", level="WARNING"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertEqual(self._post("second").status_code, 200)

    def test_pruned_versions_lose_their_files_after_commit(self):
        for i in range(11):
            with self.captureOnCommitCallbacks(execute=True):
                self._post(f"upload {i}")
        self.assertEqual(ProtocolVersion.objects.count(), 10)
        referenced = {v.html_file.name for v in ProtocolVersion.objects.all()} | {Protocol.objects.get().html_file.name}
        self.assertEqual(_stored_files(self.media_root), referenced)

    def test_delete_removes_files_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = Client().post(
                "/api/v1/protocols/delete/", {"competition_token": self.token, "protocol_type": "absolute"}
            )
        self.assertTrue(response.json()["deleted"])
        self.assertEqual(_stored_files(self.media_root), set())


class ConcurrentUploadTest(_MediaMixin, TransactionTestCase):
    def setUp(self):
        self._use_temp_media()
        self.competition = Competition.objects.create(
            title_ru="Race", date_start="2026-01-01", status=Competition.Status.APPROVED
        )
        self.token = str(self.competition.upload_token)

    def _upload(self, results, name, live):
        try:
            self._barrier.wait(timeout=10)
            response = Client(raise_request_exception=False).post(
                URL,
                {
                    "competition_token": self.token,
                    "protocol_type": "absolute",
                    "is_live": live,
                    "stage_label": name,
                    "html_file": _html(name),
                },
            )
            results[name] = response.status_code
        finally:
            connections.close_all()

    def _race(self):
        self._barrier = threading.Barrier(2)
        results: dict = {}
        threads = [
            threading.Thread(target=self._upload, args=(results, "alpha", "true")),
            threading.Thread(target=self._upload, args=(results, "beta", "false")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        return results

    def test_concurrent_first_uploads_create_one_protocol_without_500(self):
        results = self._race()
        self.assertEqual(results, {"alpha": 200, "beta": 200})
        self.assertEqual(Protocol.objects.count(), 1)
        self.assertEqual(ProtocolVersion.objects.count(), 2)

    def test_concurrent_uploads_leave_the_content_of_one_of_them(self):
        Protocol.objects.create(competition=self.competition, protocol_type="absolute", file_hash="old")
        self._race()
        protocol = Protocol.objects.get()
        with protocol.html_file.open("rb") as f:
            body = f.read().decode()
        # The file, the label and the live flag all come from the same request.
        self.assertIn(protocol.stage_label, body)
        self.assertEqual(protocol.is_live, protocol.stage_label == "alpha")
        self.assertEqual(protocol.file_hash, protocol.versions.order_by("-saved_at", "-pk").first().file_hash)
        self.assertEqual(ProtocolVersion.objects.count(), 2)
        # Every stored file is one a row points at: nothing half-written was left behind.
        referenced = {v.html_file.name for v in ProtocolVersion.objects.all()} | {protocol.html_file.name}
        self.assertEqual(_stored_files(self.media_root), referenced)
