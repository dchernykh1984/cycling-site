"""The photo gallery: albums named like "Gran Fondo 2026", one photo picked as the album's cover.

Organizers and admins make albums and fill them; an organizer manages their own albums, an admin
every album; everybody else looks. An album may belong to an event, and the event page links to it.
"""

import datetime
import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from PIL import Image

from accounts.models import User
from calendar_app.models import Competition
from gallery.images import FULL_SIDE, THUMB_SIDE, PhotoError, process
from gallery.models import Album, Photo

MEDIA = tempfile.mkdtemp()


def _user(email, role):
    return User.objects.create_user(username=email, email=email, password="password123", role=role)


def _jpeg(name="photo.jpg", size=(1600, 1067), color="orange", exif=False):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "PhoneMaker"  # Make
        data[0x0112] = 6  # Orientation: rotate 90 CW to display
        kwargs["exif"] = data.tobytes()
    image.save(buffer, format="JPEG", **kwargs)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class GalleryTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.organizer = _user("org@example.com", User.Role.ORGANIZER)
        self.other_organizer = _user("org2@example.com", User.Role.ORGANIZER)
        self.admin = _user("admin@example.com", User.Role.ADMIN)
        self.participant = _user("rider@example.com", User.Role.PARTICIPANT)

    def _album(self, title="Changan race 2026", date=datetime.date(2026, 9, 6), **kwargs):
        kwargs.setdefault("created_by", self.organizer)
        return Album.objects.create(title=title, date=date, **kwargs)

    def _photo(self, album, **kwargs):
        full, thumb = process(_jpeg())
        photo = Photo(album=album, **kwargs)
        photo.image.save(full.name, full, save=False)
        photo.thumbnail.save(thumb.name, thumb, save=False)
        photo.save()
        return photo


class ImageProcessingTests(GalleryTestCase):
    def test_a_large_photo_is_bounded_and_gets_a_thumbnail(self):
        full, thumb = process(_jpeg(size=(5000, 3000)))
        with Image.open(full) as image:
            self.assertEqual(max(image.size), FULL_SIDE)
        with Image.open(thumb) as image:
            self.assertEqual(max(image.size), THUMB_SIDE)

    def test_camera_metadata_is_dropped_and_rotation_applied(self):
        full, _ = process(_jpeg(size=(1200, 800), exif=True))
        with Image.open(full) as image:
            self.assertEqual(image.size, (800, 1200))
            self.assertNotIn(0x010F, image.getexif())

    def test_a_file_that_is_not_an_image_is_refused(self):
        with self.assertRaises(PhotoError):
            process(SimpleUploadedFile("notes.jpg", b"not a picture", content_type="image/jpeg"))

    def test_a_tiny_image_is_refused(self):
        with self.assertRaises(PhotoError):
            process(_jpeg(size=(100, 80)))


class PermissionTests(GalleryTestCase):
    def test_a_guest_and_a_participant_cannot_create_albums(self):
        response = self.client.get(reverse("gallery_album_create"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(reverse("gallery_album_create")).status_code, 403)

    def test_an_organizer_can_create_an_album(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(reverse("gallery_album_create")).status_code, 200)

    def test_an_organizer_manages_only_their_own_albums(self):
        album = self._album()
        self.client.force_login(self.other_organizer)
        self.assertEqual(self.client.get(reverse("gallery_album_edit", args=[album.pk])).status_code, 403)
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(reverse("gallery_album_edit", args=[album.pk])).status_code, 200)

    def test_an_admin_manages_every_album(self):
        album = self._album()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("gallery_album_edit", args=[album.pk])).status_code, 200)

    def test_a_participant_cannot_change_the_cover(self):
        album = self._album()
        photo = self._photo(album)
        self.client.force_login(self.participant)
        self.assertEqual(self.client.post(reverse("gallery_photo_cover", args=[photo.pk])).status_code, 403)


class CreateAlbumTests(GalleryTestCase):
    def test_an_album_takes_its_name_and_date_as_typed(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse("gallery_album_create"),
            {"title": "Gran Fondo 2026", "date": "2026-05-17", "photos": [_jpeg("a.jpg"), _jpeg("b.jpg")]},
        )
        album = Album.objects.get()
        self.assertRedirects(response, reverse("gallery_album_edit", args=[album.pk]))
        self.assertEqual(album.title, "Gran Fondo 2026")
        self.assertEqual(album.date, datetime.date(2026, 5, 17))
        self.assertEqual(album.photos.count(), 2)
        self.assertEqual(album.created_by, self.organizer)

    def test_the_first_photo_becomes_the_cover_until_another_is_picked(self):
        self.client.force_login(self.organizer)
        self.client.post(
            reverse("gallery_album_create"), {"title": "Road Race 2026", "date": "2026-06-01", "photos": [_jpeg()]}
        )
        album = Album.objects.get()
        self.assertEqual(album.cover, album.photos.first())

    def test_an_event_fills_an_empty_title_and_date(self):
        race = Competition.objects.create(
            title_ru="UBT Giant Time Trial", date_start=datetime.date(2026, 7, 12), status=Competition.Status.APPROVED
        )
        self.client.force_login(self.organizer)
        self.client.post(reverse("gallery_album_create"), {"competition": race.pk, "title": "", "date": ""})
        album = Album.objects.get()
        self.assertEqual(album.title, "UBT Giant Time Trial")
        self.assertEqual(album.date, datetime.date(2026, 7, 12))
        self.assertEqual(album.competition, race)

    def test_a_typed_title_wins_over_the_event(self):
        race = Competition.objects.create(
            title_ru="Giro", date_start=datetime.date(2026, 8, 2), status=Competition.Status.APPROVED
        )
        self.client.force_login(self.organizer)
        self.client.post(
            reverse("gallery_album_create"), {"competition": race.pk, "title": "Giro d'Almaty", "date": ""}
        )
        self.assertEqual(Album.objects.get().title, "Giro d'Almaty")

    def test_without_a_title_or_an_event_the_form_asks_for_one(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse("gallery_album_create"), {"title": "", "date": "2026-06-01"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Album.objects.exists())

    def test_a_broken_file_is_reported_and_the_rest_are_kept(self):
        self.client.force_login(self.organizer)
        bad = SimpleUploadedFile("broken.jpg", b"nope", content_type="image/jpeg")
        response = self.client.post(
            reverse("gallery_album_create"),
            {"title": "Camp 2026", "date": "2026-03-01", "photos": [_jpeg(), bad]},
            follow=True,
        )
        self.assertEqual(Album.objects.get().photos.count(), 1)
        self.assertContains(response, "broken.jpg")

    @override_settings(GALLERY_MAX_FILES_PER_UPLOAD=2)
    def test_too_many_files_at_once_are_refused(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse("gallery_album_create"),
            {"title": "Big", "date": "2026-03-01", "photos": [_jpeg(), _jpeg(), _jpeg()]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Album.objects.exists())


class CoverTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        self.album = self._album()
        self.first = self._photo(self.album, sort_order=1)
        self.second = self._photo(self.album, sort_order=2)
        self.client.force_login(self.organizer)

    def _edit(self, **data):
        payload = {"title": self.album.title, "date": "2026-09-06", **data}
        return self.client.post(reverse("gallery_album_edit", args=[self.album.pk]), payload)

    def test_without_a_pick_the_first_photo_stands_in(self):
        self.assertEqual(self.album.cover_photo, self.first)

    def test_the_cover_is_picked_in_the_album_form(self):
        self._edit(cover=self.second.pk)
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover, self.second)

    def test_the_cover_is_picked_from_the_photo_page(self):
        self.client.post(reverse("gallery_photo_cover", args=[self.second.pk]))
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover, self.second)

    def test_a_photo_of_another_album_cannot_become_the_cover(self):
        other = self._photo(self._album("Other"))
        self._edit(cover=other.pk)
        self.album.refresh_from_db()
        self.assertNotEqual(self.album.cover_id, other.pk)

    def test_deleting_the_cover_hands_it_to_the_next_photo(self):
        self.album.cover = self.first
        self.album.save()
        self._edit(delete=[self.first.pk], cover=self.first.pk)
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover, self.second)

    def test_a_deleted_photo_takes_its_files_with_it(self):
        paths = [Path(self.first.image.path), Path(self.first.thumbnail.path)]
        self._edit(delete=[self.first.pk])
        for path in paths:
            self.assertFalse(path.exists(), path)

    def test_the_cover_is_what_a_shared_link_shows(self):
        self.album.cover = self.second
        self.album.save()
        html = self.client.get(self.album.get_absolute_url()).content.decode()
        self.assertIn(self.second.image.url, html)


class GalleryPageTests(GalleryTestCase):
    def test_the_gallery_opens_the_newest_album(self):
        self._album("Old ride 2025", datetime.date(2025, 6, 1))
        newest = self._album("Changan race 2026", datetime.date(2026, 9, 6))
        self._photo(newest)
        response = self.client.get(reverse("gallery_index"))
        self.assertContains(response, "Changan race 2026")
        with translation_override("ru"):
            self.assertContains(response, gettext("Gallery %(year)s") % {"year": 2026})

    def test_other_albums_are_tabs(self):
        self._album("Gran Fondo 2026", datetime.date(2026, 5, 17))
        self._album("Changan race 2026", datetime.date(2026, 9, 6))
        response = self.client.get(reverse("gallery_index"))
        self.assertContains(response, 'class="gallery-tab active"')
        self.assertContains(response, "Gran Fondo 2026")
        self.assertContains(response, reverse("gallery_albums"))

    def test_an_empty_gallery_says_so(self):
        response = self.client.get(reverse("gallery_index"))
        self.assertEqual(response.status_code, 200)

    def test_a_hidden_album_is_not_shown_to_readers(self):
        album = self._album("Draft 2026", is_hidden=True)
        self.assertEqual(self.client.get(album.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("gallery_albums")), "Draft 2026")
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(album.get_absolute_url()).status_code, 200)

    def test_a_photo_page_steps_through_the_album(self):
        album = self._album()
        first, second = self._photo(album, sort_order=1), self._photo(album, sort_order=2)
        html = self.client.get(first.get_absolute_url()).content.decode()
        self.assertIn(reverse("gallery_photo", args=[second.pk]), html)
        self.assertIn("1 / 2", html)

    def test_the_albums_page_shows_each_cover(self):
        album = self._album()
        self._photo(album)
        chosen = self._photo(album)
        album.cover = chosen
        album.save()
        self.assertContains(self.client.get(reverse("gallery_albums")), chosen.thumbnail.url)

    def test_deleting_an_album_removes_it_and_its_photos(self):
        album = self._album()
        photo = self._photo(album)
        path = Path(photo.image.path)
        self.client.force_login(self.organizer)
        self.client.post(reverse("gallery_album_delete", args=[album.pk]))
        self.assertFalse(Album.objects.exists())
        self.assertFalse(path.exists())


class EventLinkTests(GalleryTestCase):
    def test_the_event_page_links_its_public_albums(self):
        race = Competition.objects.create(
            title_ru="Gran Fondo", date_start=datetime.date(2026, 5, 17), status=Competition.Status.APPROVED
        )
        public = self._album("Gran Fondo 2026", competition=race)
        hidden = self._album("Gran Fondo draft", competition=race, is_hidden=True)
        html = self.client.get(race.get_absolute_url()).content.decode()
        self.assertIn(public.get_absolute_url(), html)
        self.assertNotIn(hidden.get_absolute_url(), html)

    def test_an_event_without_albums_has_no_album_block(self):
        race = Competition.objects.create(
            title_ru="Quiet race", date_start=datetime.date(2026, 5, 17), status=Competition.Status.APPROVED
        )
        self.assertNotContains(self.client.get(race.get_absolute_url()), "competition-albums")


class NavigationAndSitemapTests(GalleryTestCase):
    def test_every_page_links_the_gallery(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertIn(reverse("gallery_index"), html)

    def test_public_albums_are_in_the_sitemap_and_hidden_ones_are_not(self):
        public = self._album("Public 2026")
        hidden = self._album("Hidden 2026", is_hidden=True)
        body = self.client.get(reverse("sitemap_section", args=["gallery"])).content.decode()
        self.assertIn(public.get_absolute_url(), body)
        self.assertNotIn(hidden.get_absolute_url(), body)

    def test_the_gallery_strings_are_translated(self):
        for locale in ("ru", "kk"):
            with translation_override(locale):
                for msgid in ("Gallery", "Cover photo", "Make cover", "New album", "View more"):
                    self.assertNotEqual(gettext(msgid), msgid, f"{msgid!r} in {locale}")
