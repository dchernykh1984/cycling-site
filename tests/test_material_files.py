"""An event's additional materials as files: uploaded on the edit page, opened from the event's page, let go."""

import datetime
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext

from accounts.models import User
from calendar_app.models import Competition, CompetitionMaterial

MEDIA = tempfile.mkdtemp(prefix="material-files-")


def _pdf(name="results.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 results", content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA)
class MaterialFileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        # the least-privileged person who may edit the event: its author, a participant
        self.author = User.objects.create_user(
            username="mat-author", email="mat-author@example.com", password="pw", role=User.Role.PARTICIPANT
        )
        self.comp = Competition.objects.create(
            title_ru="Race with files",
            date_start=datetime.date(2026, 7, 1),
            status=Competition.Status.APPROVED,
            submitted_by=self.author,
        )
        self.client.force_login(self.author)

    def _post(self, row, *, saved=None):
        payload = {
            "title_ru": "Race with files",
            "date_start": "2026-07-01",
            "materials-TOTAL_FORMS": "1",
            "materials-INITIAL_FORMS": "1" if saved else "0",
            "materials-MIN_NUM_FORMS": "0",
            "materials-MAX_NUM_FORMS": "1000",
        }
        if saved:
            payload["materials-0-id"] = str(saved.pk)
        payload.update({f"materials-0-{field}": value for field, value in row.items()})
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("competition_edit", args=[self.comp.pk]), payload)

    def _saved_with_file(self):
        self._post({"title": "Results", "url": "", "file": _pdf()})
        return self.comp.materials.get()

    def test_a_file_uploaded_with_a_name_is_a_button_on_the_event_s_page(self):
        material = self._saved_with_file()
        self.assertEqual(material.url, "")
        self.assertTrue(Path(material.file.path).is_file())
        page = self.client.get(reverse("competition_detail", args=[self.comp.pk]))
        self.assertContains(page, f'href="{material.file.url}"')
        self.assertTrue(material.file.url.startswith("/media/competitions/materials/"))

    def test_a_presentation_is_a_material_too(self):
        upload = SimpleUploadedFile("talk.pptx", b"PK\x03\x04 slides", content_type="application/octet-stream")
        self._post({"title": "Briefing", "url": "", "file": upload})
        self.assertTrue(self.comp.materials.get().file.name.endswith(".pptx"))

    def test_a_file_of_a_kind_the_site_does_not_keep_is_refused(self):
        upload = SimpleUploadedFile("tool.exe", b"MZ", content_type="application/octet-stream")
        response = self._post({"title": "Tool", "url": "", "file": upload})
        self.assertFalse(self.comp.materials.exists())
        self.assertTrue(response.context["material_formset"].errors[0]["file"])

    def test_a_file_that_would_take_the_disk_s_last_reserve_is_refused(self):
        reserve = 200 * 1024 * 1024
        with (
            override_settings(GALLERY_DISK_RESERVE_MB=200),
            mock.patch("cycling_site.system.media_disk", return_value=mock.Mock(free=reserve + 10)),
        ):
            response = self._post({"title": "Results", "url": "", "file": _pdf()})
        self.assertFalse(self.comp.materials.exists())
        self.assertEqual(
            response.context["material_formset"].errors[0]["file"],
            [gettext("The site's disk is nearly full: the file cannot be kept now.")],
        )

    def test_a_name_without_a_link_or_a_file_is_refused(self):
        response = self._post({"title": "Nothing", "url": ""})
        self.assertFalse(self.comp.materials.exists())
        self.assertEqual(
            response.context["material_formset"].errors[0]["url"], [gettext("Add a link or a file to this material.")]
        )

    def test_a_file_uploaded_on_a_link_s_row_takes_its_place(self):
        link = CompetitionMaterial.objects.create(competition=self.comp, title="Photos", url="https://photos.example/a")
        self._post({"title": "Photos", "url": "https://photos.example/a", "file": _pdf("photos.pdf")}, saved=link)
        link.refresh_from_db()
        self.assertEqual(link.url, "")
        self.assertEqual(link.href, link.file.url)

    def test_a_row_saved_again_without_a_new_file_keeps_its_file(self):
        material = self._saved_with_file()
        self._post({"title": "Final results", "url": ""}, saved=material)
        renamed = self.comp.materials.get()
        self.assertEqual((renamed.title, renamed.file.name), ("Final results", material.file.name))
        self.assertTrue(Path(renamed.file.path).is_file())

    def test_a_link_given_on_a_file_s_row_lets_the_file_go_from_the_disk(self):
        material = self._saved_with_file()
        path = Path(material.file.path)
        self._post({"title": "Results", "url": "https://results.example/1"}, saved=material)
        material.refresh_from_db()
        self.assertEqual((material.url, material.file.name), ("https://results.example/1", ""))
        self.assertFalse(path.exists())

    def test_a_new_file_on_a_file_s_row_lets_the_old_one_go(self):
        material = self._saved_with_file()
        old = Path(material.file.path)
        self._post({"title": "Results", "url": "", "file": _pdf("final.pdf")}, saved=material)
        material.refresh_from_db()
        self.assertTrue(Path(material.file.path).is_file())
        self.assertFalse(old.exists())

    def test_removing_a_file_s_row_deletes_its_file(self):
        material = self._saved_with_file()
        path = Path(material.file.path)
        self._post({"title": "Results", "url": "", "DELETE": "on"}, saved=material)
        self.assertFalse(self.comp.materials.exists())
        self.assertFalse(path.exists())


class MaterialInAdminTests(TestCase):
    def test_the_admin_refuses_a_material_without_a_link_or_a_file(self):
        from calendar_app.admin import CompetitionMaterialInline

        form_class = CompetitionMaterialInline.form
        form = form_class(data={"title": "Nothing", "url": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)


class PresentationsInEveryFileFieldTests(TestCase):
    def test_every_file_field_of_the_event_takes_a_presentation_in_each_format_it_is_made_in(self):
        from calendar_app.forms import validate_document

        for ext in ("ppt", "pptx", "pps", "ppsx", "odp", "key"):
            with self.subTest(ext=ext):
                upload = SimpleUploadedFile(f"talk.{ext}", b"slides", content_type="application/octet-stream")
                self.assertIs(validate_document(upload), upload)
