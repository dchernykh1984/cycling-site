""" "Download all": a registration's album or a bib's photos as one ZIP of originals, streamed from
storage one archive at a time, on the page and over the API. The storage is a fake."""

import io
import uuid
import zipfile
from threading import BoundedSemaphore
from unittest import mock
from urllib.parse import quote

from django.test import override_settings
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from accounts.models import User
from event_photos import actions, archive
from event_photos.dropbox import DropboxError
from event_photos.models import IndexedPhoto
from tests.test_event_photos import MEDIA, EventPhotosTestCase, FakeAdapter, _index, _photo


def _zip(response) -> zipfile.ZipFile:
    body = b"".join(response.streaming_content)
    return zipfile.ZipFile(io.BytesIO(body))


@override_settings(EVENT_PHOTOS_ADAPTER="tests.test_event_photos.FakeAdapter", MEDIA_ROOT=MEDIA)
class ArchiveTests(EventPhotosTestCase):
    def setUp(self):
        super().setUp()
        # A test that fails while holding the slot must not make the next ones "busy".
        slots = mock.patch.object(archive, "_SLOTS", BoundedSemaphore(1))
        slots.start()
        self.addCleanup(slots.stop)
        self.athlete = User.objects.create_user(username="a@x.kz", email="a@x.kz", password="pw", role="participant")
        self.stranger = User.objects.create_user(username="s@x.kz", email="s@x.kz", password="pw", role="participant")
        self.reg = self._registration()
        self.reg.user = self.athlete
        self.reg.save(update_fields=["user"])
        self._bib(self.reg, "12")
        self._publish(_index([_photo(1, [("12", "accepted", "ocr")]), _photo(2, [("12", "candidate", "ocr")])]))
        FakeAdapter.files.update({"IMG_0001.jpg": b"first original", "IMG_0002.jpg": b"second original"})

    def _url(self, name, *args):
        return reverse(f"event_photos:{name}", args=[self.race.pk, *args])

    def _bib_url(self, bib="12"):
        return f"{self._url('bib_archive')}?bib={bib}"

    def test_my_album_downloads_as_one_zip_of_its_originals(self):
        self.client.force_login(self.athlete)
        response = self.client.get(self._url("registration_archive", self.reg.pk))
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("Alatau XCO - Ivanov Ivan.zip", response["Content-Disposition"])
        files = _zip(response)
        self.assertEqual(sorted(files.namelist()), ["IMG_0001.jpg", "IMG_0002.jpg"])
        self.assertEqual(files.read("IMG_0001.jpg"), b"first original")

        photo = IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=3))
        actions.decide(self.reg, photo, "not_me", self.athlete)
        response = self.client.get(self._url("registration_archive", self.reg.pk))
        self.assertEqual(_zip(response).namelist(), ["IMG_0001.jpg"])

    def test_only_the_album_owner_downloads_it_and_a_guest_is_sent_to_sign_in(self):
        url = self._url("registration_archive", self.reg.pk)
        self.assertIn("/login/", self.client.get(url)["Location"])
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_a_bib_search_downloads_its_photos_for_signed_in_readers_only(self):
        self.assertIn("/login/", self.client.get(self._bib_url())["Location"])
        self.client.force_login(self.stranger)
        # The search shows accepted matches only; the archive holds exactly what it shows.
        self.assertEqual(_zip(self.client.get(self._bib_url())).namelist(), ["IMG_0001.jpg"])
        self.assertEqual(self.client.get(self._url("bib_archive")).status_code, 404)
        # Nothing found: no empty archive.
        self.assertEqual(self.client.get(self._bib_url("99")).status_code, 404)

    def test_both_pages_offer_the_archive_with_its_size(self):
        self.client.force_login(self.athlete)
        page = self.client.get(self._url("registration", self.reg.pk))
        self.assertContains(page, self._url("registration_archive", self.reg.pk))
        self.assertContains(page, 'rel="nofollow"')
        search = self.client.get(f"{self._url('event')}?bib=12")
        self.assertContains(search, self._bib_url())
        nothing = self.client.get(f"{self._url('event')}?bib=99")
        self.assertNotContains(nothing, self._url("bib_archive"))

    def test_a_guest_searching_is_offered_sign_in_and_brought_back_to_the_search(self):
        search = self.client.get(f"{self._url('event')}?bib=12")
        self.assertNotContains(search, self._url("bib_archive"))
        self.assertContains(
            search, f"{reverse('account_login')}?next={quote(self._url('event') + '?bib=12', safe='/')}"
        )

    def test_a_photo_the_storage_cannot_give_is_listed_with_its_link(self):
        del FakeAdapter.files["IMG_0002.jpg"]
        self.client.force_login(self.athlete)
        files = _zip(self.client.get(self._url("registration_archive", self.reg.pk)))
        with translation_override("ru"):
            note_name = gettext("missing-photos.txt")
        self.assertEqual(sorted(files.namelist()), sorted(["IMG_0001.jpg", note_name]))
        note = files.read(note_name).decode()
        self.assertIn("IMG_0002.jpg", note)
        self.assertIn("preview=IMG_0002.jpg", note)

    @override_settings(PHOTO_ARCHIVE_MAX_FILE_BYTES=1001)
    def test_an_original_over_the_file_limit_is_listed_without_being_read(self):
        self.client.force_login(self.athlete)
        with mock.patch.object(FakeAdapter, "read_file", wraps=FakeAdapter().read_file) as reads:
            files = _zip(self.client.get(self._url("registration_archive", self.reg.pk)))
        # IMG_0001 is 1001 bytes by its index, IMG_0002 1002: only the first is asked for.
        self.assertEqual([c.args[1] for c in reads.call_args_list], ["IMG_0001.jpg"])
        self.assertIn("IMG_0001.jpg", files.namelist())
        self.assertNotIn("IMG_0002.jpg", files.namelist())

    def test_a_storage_hiccup_is_waited_out_once(self):
        self.client.force_login(self.athlete)
        answers = [DropboxError("throttled", retry_after=3), b"first original", b"second original"]
        with (
            mock.patch.object(FakeAdapter, "read_file", side_effect=answers),
            mock.patch("event_photos.archive.time.sleep") as sleep,
        ):
            files = _zip(self.client.get(self._url("registration_archive", self.reg.pk)))
        sleep.assert_called_once_with(3)
        self.assertEqual(sorted(files.namelist()), ["IMG_0001.jpg", "IMG_0002.jpg"])

    def test_one_archive_at_a_time_and_the_slot_is_freed_when_it_ends(self):
        self.client.force_login(self.athlete)
        url = self._url("registration_archive", self.reg.pk)
        first = self.client.get(url)  # not read yet: still being sent
        busy = self.client.get(url, follow=True)
        with translation_override("ru"):
            self.assertContains(busy, gettext("Another archive is being made right now. Try again in a minute."))
        self.athlete.api_token = uuid.uuid4()
        self.athlete.save(update_fields=["api_token"])
        api = self.client.get(
            f"/api/v1/event-photos/registrations/{self.reg.pk}/photos/archive",
            HTTP_AUTHORIZATION=f"Bearer {self.athlete.api_token}",
        )
        self.assertEqual((api.status_code, api["Retry-After"]), (503, "60"))
        _zip(first)  # read to the end: the response closes and frees the slot
        self.assertEqual(self.client.get(url)["Content-Type"], "application/zip")

    def test_a_reader_who_leaves_frees_the_slot(self):
        photos = IndexedPhoto.objects.select_related("album")
        body = archive.Archive(photos)
        next(iter(body))  # the first original sent, then the reader goes away
        with self.assertRaises(archive.ArchiveBusyError):
            archive.Archive(photos)
        body.close()  # what Django calls on the response's body when the connection ends
        archive.Archive(photos).close()

    @override_settings(PHOTO_ARCHIVE_MAX_BYTES=2000)
    def test_too_big_an_archive_is_not_offered_and_is_refused(self):
        self.client.force_login(self.athlete)
        page = self.client.get(self._url("registration", self.reg.pk))
        self.assertNotContains(page, self._url("registration_archive", self.reg.pk))
        with translation_override("ru"):
            self.assertContains(page, gettext("Too many photos for one archive (%(size)s): open them one by one.")[:20])
        refused = self.client.get(self._url("registration_archive", self.reg.pk))
        self.assertEqual(refused.status_code, 302)
        self.athlete.api_token = uuid.uuid4()
        self.athlete.save(update_fields=["api_token"])
        api = self.client.get(
            f"/api/v1/event-photos/registrations/{self.reg.pk}/photos/archive",
            HTTP_AUTHORIZATION=f"Bearer {self.athlete.api_token}",
        )
        self.assertEqual(api.status_code, 413)

    def test_the_api_gives_both_archives_to_a_token_and_none_without_one(self):
        self.stranger.api_token = uuid.uuid4()
        self.stranger.save(update_fields=["api_token"])
        bib_url = f"/api/v1/event-photos/competitions/{self.race.pk}/photos/archive?bib=12"
        self.assertEqual(self.client.get(bib_url).status_code, 401)
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.stranger.api_token}"}
        self.assertEqual(_zip(self.client.get(bib_url, **headers)).namelist(), ["IMG_0001.jpg"])
        self.assertEqual(self.client.get(bib_url.replace("bib=12", "bib=99"), **headers).status_code, 404)
        mine = f"/api/v1/event-photos/registrations/{self.reg.pk}/photos/archive"
        self.assertEqual(self.client.get(mine, **headers).status_code, 404)
        self.athlete.api_token = uuid.uuid4()
        self.athlete.save(update_fields=["api_token"])
        response = self.client.get(mine, HTTP_AUTHORIZATION=f"Bearer {self.athlete.api_token}")
        self.assertEqual(len(_zip(response).namelist()), 2)


def test_two_photographers_files_of_one_name_both_fit():
    taken: set[str] = set()
    names = [archive._unique(name, taken) for name in ("IMG_0001.jpg", "img_0001.JPG", "IMG_0001.jpg", "README")]
    assert names == ["IMG_0001.jpg", "img_0001-2.JPG", "IMG_0001-3.jpg", "README"]


@override_settings(EVENT_PHOTOS_ADAPTER="tests.test_event_photos.FakeAdapter", MEDIA_ROOT=MEDIA)
class ArchiveNameTests(EventPhotosTestCase):
    def test_a_title_with_a_line_break_gives_a_one_line_file_name(self):
        athlete = User.objects.create_user(username="a@x.kz", email="a@x.kz", password="pw", role="participant")
        self.race.title_ru = "Alatau\r\nXCO"
        self.race.save(update_fields=["title_ru"])
        reg = self._registration()
        reg.user = athlete
        reg.save(update_fields=["user"])
        self._bib(reg, "12")
        self._publish(_index([_photo(1, [("12", "accepted", "ocr")])]))
        FakeAdapter.files["IMG_0001.jpg"] = b"first original"
        self.client.force_login(athlete)
        url = reverse("event_photos:registration_archive", args=[self.race.pk, reg.pk])
        response = self.client.get(url)
        self.assertIn("Alatau XCO - Ivanov Ivan.zip", response["Content-Disposition"])
        self.assertEqual(_zip(response).namelist(), ["IMG_0001.jpg"])
