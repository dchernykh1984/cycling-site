import hashlib
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from calendar_app.models import Competition
from protocols.models import Protocol, ProtocolVersion

HTML = b"<html><body><p>Test protocol</p></body></html>"


def _html_file(content: bytes = HTML, name: str = "protocol.html") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="text/html")


def _make_competition(status: str = Competition.Status.APPROVED) -> Competition:
    return Competition.objects.create(
        title_ru="Test Race",
        date_start="2026-01-01",
        status=status,
    )


class UploadProtocolTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self._settings = override_settings(
            MAX_PROTOCOL_SIZE_MB=5,
            MEDIA_ROOT=self.media_root,
        )
        self._settings.enable()
        self.client = Client()
        self.competition = _make_competition()
        self.url = "/api/v1/protocols/upload/"

    def tearDown(self):
        self._settings.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _post(self, **kwargs):
        data = {
            "competition_token": str(self.competition.upload_token),
            "protocol_type": "absolute",
            "is_live": "true",
            "html_file": _html_file(),
        }
        data.update(kwargs)
        return self.client.post(self.url, data)

    def test_upload_creates_protocol(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Protocol.objects.count(), 1)

    def test_upload_creates_version(self):
        self._post()
        self.assertEqual(ProtocolVersion.objects.count(), 1)

    def test_upload_returns_id_and_hash(self):
        response = self._post()
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("file_hash", data)
        self.assertEqual(data["file_hash"], hashlib.sha256(HTML).hexdigest())

    def test_missing_competition_token_returns_422(self):
        data = {
            "protocol_type": "absolute",
            "is_live": "true",
            "html_file": _html_file(),
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 422)

    def test_invalid_competition_token_returns_401(self):
        response = self._post(competition_token="00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, 401)

    def test_malformed_competition_token_returns_401(self):
        response = self._post(competition_token="not-a-uuid")
        self.assertEqual(response.status_code, 401)

    def test_non_approved_competition_returns_401(self):
        pending = _make_competition(status=Competition.Status.PENDING_APPROVAL)
        response = self._post(competition_token=str(pending.upload_token))
        self.assertEqual(response.status_code, 401)

    def test_invalid_protocol_type_returns_400(self):
        response = self._post(protocol_type="invalid")
        self.assertEqual(response.status_code, 400)

    def test_missing_html_file_returns_422(self):
        response = self.client.post(
            self.url,
            {
                "competition_token": str(self.competition.upload_token),
                "protocol_type": "absolute",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_file_too_large_returns_400(self):
        large = SimpleUploadedFile("big.html", b"x" * (6 * 1024 * 1024), content_type="text/html")
        with override_settings(MAX_PROTOCOL_SIZE_MB=5, MEDIA_ROOT=self.media_root):
            response = self._post(html_file=large)
        self.assertEqual(response.status_code, 400)

    def test_wrong_content_type_returns_400(self):
        f = SimpleUploadedFile("p.html", HTML, content_type="application/pdf")
        response = self._post(html_file=f)
        self.assertEqual(response.status_code, 400)

    def test_empty_content_type_returns_400(self):
        f = SimpleUploadedFile("p.html", HTML, content_type="")
        response = self._post(html_file=f)
        self.assertEqual(response.status_code, 400)

    def test_html_with_charset_accepted(self):
        f = SimpleUploadedFile("p.html", HTML, content_type="text/html; charset=utf-8")
        response = self._post(html_file=f)
        self.assertEqual(response.status_code, 200)

    def test_invalid_is_live_returns_422(self):
        response = self._post(is_live="ture")
        self.assertEqual(response.status_code, 422)

    def test_second_upload_updates_protocol(self):
        self._post()
        second = b"<html><body>Updated</body></html>"
        self._post(html_file=_html_file(second))
        self.assertEqual(Protocol.objects.count(), 1)
        protocol = Protocol.objects.get()
        self.assertEqual(protocol.file_hash, hashlib.sha256(second).hexdigest())

    def test_second_upload_adds_version(self):
        self._post()
        self._post()
        self.assertEqual(ProtocolVersion.objects.count(), 2)

    def test_purge_keeps_max_10_versions(self):
        for _ in range(12):
            self._post()
        self.assertLessEqual(ProtocolVersion.objects.count(), 10)

    def test_is_live_false(self):
        self._post(is_live="false")
        self.assertFalse(Protocol.objects.get().is_live)

    def test_is_live_0(self):
        self._post(is_live="0")
        self.assertFalse(Protocol.objects.get().is_live)

    def test_is_live_true(self):
        self._post(is_live="true")
        self.assertTrue(Protocol.objects.get().is_live)

    def test_stage_label_saved(self):
        self._post(stage_label="Lap 3")
        self.assertEqual(Protocol.objects.get().stage_label, "Lap 3")

    def test_group_protocol_type(self):
        self._post(protocol_type="group")
        self.assertEqual(Protocol.objects.get().protocol_type, "group")

    def test_absolute_and_group_are_separate_protocols(self):
        self._post(protocol_type="absolute")
        self._post(protocol_type="group")
        self.assertEqual(Protocol.objects.count(), 2)

    def test_get_method_returns_405(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)


class ProtocolLastUpdatedTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.competition = _make_competition()

    def _create_protocol(self, is_live: bool = True) -> Protocol:
        return Protocol.objects.create(
            competition=self.competition,
            protocol_type="absolute",
            is_live=is_live,
            file_hash="abc123def456",
        )

    def test_returns_last_updated_and_hash(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/api/protocols/{protocol.pk}/last_updated/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("last_updated", data)
        self.assertEqual(data["file_hash"], "abc123def456")
        self.assertTrue(data["is_live"])

    def test_is_live_false(self):
        protocol = self._create_protocol(is_live=False)
        response = self.client.get(f"/api/protocols/{protocol.pk}/last_updated/")
        self.assertFalse(response.json()["is_live"])

    def test_nonexistent_protocol_returns_404(self):
        response = self.client.get("/api/protocols/99999/last_updated/")
        self.assertEqual(response.status_code, 404)

    def test_non_approved_competition_returns_404(self):
        pending = _make_competition(status=Competition.Status.PENDING_APPROVAL)
        protocol = Protocol.objects.create(
            competition=pending,
            protocol_type="absolute",
            is_live=True,
            file_hash="abc",
        )
        response = self.client.get(f"/api/protocols/{protocol.pk}/last_updated/")
        self.assertEqual(response.status_code, 404)

    def _protocol_for_flagged_competition(self, **flags):
        comp = _make_competition()
        for field, value in flags.items():
            setattr(comp, field, value)
        comp.save(update_fields=list(flags))
        return Protocol.objects.create(competition=comp, protocol_type="absolute", is_live=True, file_hash="abc")

    def test_hidden_competition_returns_404(self):
        protocol = self._protocol_for_flagged_competition(is_hidden=True)
        self.assertEqual(self.client.get(f"/api/protocols/{protocol.pk}/last_updated/").status_code, 404)

    def test_deleted_competition_returns_404(self):
        protocol = self._protocol_for_flagged_competition(is_deleted=True)
        self.assertEqual(self.client.get(f"/api/protocols/{protocol.pk}/last_updated/").status_code, 404)


class ProtocolHtmlTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self._settings = override_settings(MEDIA_ROOT=self.media_root)
        self._settings.enable()
        self.client = Client()
        self.competition = _make_competition()

    def tearDown(self):
        self._settings.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _create_protocol(self, content: bytes = HTML) -> Protocol:
        protocol = Protocol(
            competition=self.competition,
            protocol_type="absolute",
            is_live=True,
            file_hash=hashlib.sha256(content).hexdigest(),
        )
        protocol.html_file.save("protocol.html", ContentFile(content), save=False)
        protocol.save()
        return protocol

    def test_serves_html_content(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Test protocol", response.content)

    def test_content_type_is_html(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertIn("text/html", response["Content-Type"])

    def test_sets_nosniff_header(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_sets_csp_header(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])

    def test_sets_cache_control_no_store(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_sets_xframe_sameorigin(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertEqual(response.get("X-Frame-Options"), "SAMEORIGIN")

    def test_protocol_without_file_returns_404(self):
        protocol = Protocol.objects.create(
            competition=self.competition,
            protocol_type="absolute",
            is_live=True,
            file_hash="",
        )
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_returns_404(self):
        response = self.client.get("/protocols/99999/html/")
        self.assertEqual(response.status_code, 404)

    def test_non_approved_competition_returns_404(self):
        pending = _make_competition(status=Competition.Status.PENDING_APPROVAL)
        protocol = Protocol(
            competition=pending,
            protocol_type="absolute",
            is_live=True,
            file_hash="abc",
        )
        protocol.html_file.save("protocol.html", ContentFile(HTML), save=False)
        protocol.save()
        response = self.client.get(f"/protocols/{protocol.pk}/html/")
        self.assertEqual(response.status_code, 404)

    def _html_protocol_for_flagged_competition(self, **flags):
        comp = _make_competition()
        for field, value in flags.items():
            setattr(comp, field, value)
        comp.save(update_fields=list(flags))
        protocol = Protocol(competition=comp, protocol_type="absolute", is_live=True, file_hash="abc")
        protocol.html_file.save("protocol.html", ContentFile(HTML), save=False)
        protocol.save()
        return protocol

    def test_hidden_competition_returns_404(self):
        protocol = self._html_protocol_for_flagged_competition(is_hidden=True)
        self.assertEqual(self.client.get(f"/protocols/{protocol.pk}/html/").status_code, 404)

    def test_deleted_competition_returns_404(self):
        protocol = self._html_protocol_for_flagged_competition(is_deleted=True)
        self.assertEqual(self.client.get(f"/protocols/{protocol.pk}/html/").status_code, 404)


class ProtocolDetailTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self._settings = override_settings(MEDIA_ROOT=self.media_root)
        self._settings.enable()
        self.client = Client()
        self.competition = _make_competition()

    def tearDown(self):
        self._settings.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _create_protocol(self, is_live: bool = True) -> Protocol:
        protocol = Protocol(
            competition=self.competition,
            protocol_type="absolute",
            is_live=is_live,
            file_hash="abc",
        )
        protocol.html_file.save("p.html", ContentFile(HTML), save=False)
        protocol.save()
        return protocol

    def test_detail_page_renders(self):
        protocol = self._create_protocol()
        response = self.client.get(f"/protocols/{protocol.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Race")

    def test_live_protocol_shows_polling_script(self):
        protocol = self._create_protocol(is_live=True)
        response = self.client.get(f"/protocols/{protocol.pk}/")
        self.assertContains(response, "poll")

    def test_non_live_shows_final_results(self):
        protocol = self._create_protocol(is_live=False)
        response = self.client.get(f"/protocols/{protocol.pk}/")
        self.assertNotContains(response, "live-banner")

    def test_nonexistent_returns_404(self):
        response = self.client.get("/protocols/99999/")
        self.assertEqual(response.status_code, 404)

    def test_non_approved_competition_returns_404(self):
        pending = _make_competition(status=Competition.Status.PENDING_APPROVAL)
        protocol = Protocol(
            competition=pending,
            protocol_type="absolute",
            is_live=True,
            file_hash="abc",
        )
        protocol.html_file.save("p.html", ContentFile(HTML), save=False)
        protocol.save()
        response = self.client.get(f"/protocols/{protocol.pk}/")
        self.assertEqual(response.status_code, 404)

    def _detail_protocol_for_flagged_competition(self, **flags):
        comp = _make_competition()
        for field, value in flags.items():
            setattr(comp, field, value)
        comp.save(update_fields=list(flags))
        protocol = Protocol(competition=comp, protocol_type="absolute", is_live=True, file_hash="abc")
        protocol.html_file.save("p.html", ContentFile(HTML), save=False)
        protocol.save()
        return protocol

    def test_hidden_competition_returns_404(self):
        protocol = self._detail_protocol_for_flagged_competition(is_hidden=True)
        self.assertEqual(self.client.get(f"/protocols/{protocol.pk}/").status_code, 404)

    def test_deleted_competition_returns_404(self):
        protocol = self._detail_protocol_for_flagged_competition(is_deleted=True)
        self.assertEqual(self.client.get(f"/protocols/{protocol.pk}/").status_code, 404)

    @override_settings(LANGUAGE_CODE="en")
    def test_version_history_shown(self):
        protocol = self._create_protocol()
        version = ProtocolVersion(protocol=protocol, file_hash="ver1hash")
        version.html_file.save("v_p.html", ContentFile(HTML), save=True)
        response = self.client.get(f"/protocols/{protocol.pk}/")
        self.assertContains(response, "Update history")


class ProtocolModelTest(TestCase):
    def setUp(self):
        self.competition = _make_competition()

    def test_protocol_str(self):
        protocol = Protocol(
            competition=self.competition,
            protocol_type="absolute",
        )
        self.assertIn("Test Race", str(protocol))
        self.assertIn("absolute", str(protocol))
