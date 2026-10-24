"""The gallery over the API (issue #365): readers see what the pages show them, admins change it."""

import datetime
import uuid
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from api.endpoints.gallery import MAX_CAPTION_LENGTH
from api.tests import ApiTestMixin
from calendar_app.models import Competition
from gallery.models import Album, Photo
from tests.test_gallery import GalleryTestCase, _jpeg


def _token(user):
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return user


class GalleryReadApiTests(ApiTestMixin, GalleryTestCase):
    def setUp(self):
        super().setUp()
        _token(self.admin)
        _token(self.participant)
        self.album = self._album(title_ru="Gonka", title_en="The race")
        self.first = self._photo(self.album, sort_order=1, caption_en="Start")
        self.second = self._photo(self.album, sort_order=2)
        self.hidden = self._album(title="Not ready", date=datetime.date(2026, 10, 1), is_hidden=True)

    def test_anybody_lists_the_public_albums_newest_first(self):
        older = self._album(title="Spring", date=datetime.date(2026, 3, 1))
        response = self.get("/api/v1/gallery/albums/")
        self.assertEqual(response.status_code, 200)
        albums = response.json()
        self.assertEqual([a["id"] for a in albums], [self.album.pk, older.pk])
        first = albums[0]
        self.assertEqual(first["title"]["en"], "The race")
        self.assertEqual(first["photo_count"], 2)
        self.assertEqual(first["cover_photo_id"], self.first.pk)

    def test_a_hidden_album_is_listed_and_opened_only_for_an_admin(self):
        for user in (None, self.participant):
            ids = [a["id"] for a in self.get("/api/v1/gallery/albums/", user=user).json()]
            self.assertNotIn(self.hidden.pk, ids)
            self.assertEqual(self.get(f"/api/v1/gallery/albums/{self.hidden.pk}", user=user).status_code, 404)
        ids = [a["id"] for a in self.get("/api/v1/gallery/albums/", user=self.admin).json()]
        self.assertIn(self.hidden.pk, ids)
        self.assertEqual(self.get(f"/api/v1/gallery/albums/{self.hidden.pk}", user=self.admin).status_code, 200)

    def test_an_album_brings_its_photos_in_order_with_their_files(self):
        album = self.get(f"/api/v1/gallery/albums/{self.album.pk}").json()
        self.assertEqual([p["id"] for p in album["photos"]], [self.first.pk, self.second.pk])
        photo = album["photos"][0]
        self.assertEqual(photo["caption"]["en"], "Start")
        self.assertEqual(photo["image_url"], f"http://testserver{self.first.image.url}")
        self.assertEqual(photo["thumbnail_url"], f"http://testserver{self.first.thumbnail.url}")
        self.assertEqual((photo["width"], photo["height"]), (self.first.width, self.first.height))

    def test_a_photo_is_read_on_its_own_unless_its_album_is_hidden(self):
        self.assertEqual(self.get(f"/api/v1/gallery/photos/{self.second.pk}").json()["id"], self.second.pk)
        hidden_photo = self._photo(self.hidden)
        self.assertEqual(self.get(f"/api/v1/gallery/photos/{hidden_photo.pk}").status_code, 404)
        self.assertEqual(self.get(f"/api/v1/gallery/photos/{hidden_photo.pk}", user=self.admin).status_code, 200)
        self.assertEqual(self.get("/api/v1/gallery/photos/999999").status_code, 404)

    def test_an_album_names_its_event_only_while_the_event_is_public(self):
        event = Competition.objects.create(
            title_ru="Gran Fondo", date_start="2026-09-06", status=Competition.Status.APPROVED
        )
        self.album.competition = event
        self.album.save()
        self.assertEqual(self.get(f"/api/v1/gallery/albums/{self.album.pk}").json()["competition_id"], event.pk)
        event.invite_only = True
        event.save()
        self.assertIsNone(self.get(f"/api/v1/gallery/albums/{self.album.pk}").json()["competition_id"])
        listed = {a["id"]: a for a in self.get("/api/v1/gallery/albums/").json()}
        self.assertIsNone(listed[self.album.pk]["competition_id"])
        # An admin keeps seeing the link, to manage it.
        self.assertEqual(
            self.get(f"/api/v1/gallery/albums/{self.album.pk}", user=self.admin).json()["competition_id"], event.pk
        )

    def test_a_wrong_token_is_refused_even_for_reading(self):
        response = self.client.get("/api/v1/gallery/albums/", HTTP_AUTHORIZATION=f"Bearer {uuid.uuid4()}")
        self.assertEqual(response.status_code, 401)


class GalleryWriteApiTests(ApiTestMixin, GalleryTestCase):
    """Only admins and the owner change the gallery, through the page's own rules."""

    def setUp(self):
        super().setUp()
        for user in (self.admin, self.organizer, self.participant):
            _token(user)
        self.album = self._album(title_ru="Gonka", title_kk="", title_en="The race")

    def _upload(self, album, *files, user=None):
        return self.client.post(
            f"/api/v1/gallery/albums/{album.pk}/photos/", {"photos": list(files)}, **self.auth(user or self.admin)
        )

    def test_nobody_below_admin_changes_anything(self):
        photo = self._photo(self.album)
        calls = [
            ("post", "/api/v1/gallery/albums/", {"title": {"ru": "X"}, "date": "2026-10-01"}),
            ("patch", f"/api/v1/gallery/albums/{self.album.pk}", {"is_hidden": True}),
            ("delete", f"/api/v1/gallery/albums/{self.album.pk}", None),
            ("patch", f"/api/v1/gallery/photos/{photo.pk}", {"caption": {"ru": "X"}}),
            ("delete", f"/api/v1/gallery/photos/{photo.pk}", None),
        ]
        for user in (self.organizer, self.participant):
            for method, url, body in calls:
                response = (
                    getattr(self, method)(url, body, user=user) if body else getattr(self, method)(url, user=user)
                )
                self.assertEqual(response.status_code, 403, (user.role, method, url))
            self.assertEqual(self._upload(self.album, _jpeg(), user=user).status_code, 403)
        self.assertEqual(
            self.client.post("/api/v1/gallery/albums/", {}, content_type="application/json").status_code, 401
        )
        self.album.refresh_from_db()
        self.assertFalse(self.album.is_hidden)
        self.assertTrue(Photo.objects.filter(pk=photo.pk).exists())

    def test_an_admin_creates_an_album(self):
        response = self.post(
            "/api/v1/gallery/albums/",
            {"title": {"ru": "Osen", "en": "Autumn"}, "date": "2026-10-01", "is_hidden": True},
            user=self.admin,
        )
        self.assertEqual(response.status_code, 201, response.content)
        album = Album.objects.get(pk=response.json()["id"])
        self.assertEqual((album.title_ru, album.title_kk, album.title_en), ("Osen", "", "Autumn"))
        self.assertEqual(album.date, datetime.date(2026, 10, 1))
        self.assertTrue(album.is_hidden)
        self.assertEqual(album.created_by, self.admin)

    def test_an_album_takes_an_empty_title_and_date_from_its_public_event(self):
        event = Competition.objects.create(
            title_ru="Gran Fondo RU",
            title_en="Gran Fondo",
            date_start="2026-09-06",
            status=Competition.Status.APPROVED,
        )
        response = self.post("/api/v1/gallery/albums/", {"competition_id": event.pk}, user=self.admin)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["title"]["ru"], body["title"]["en"]), ("Gran Fondo RU", "Gran Fondo"))
        self.assertEqual((body["date"], body["competition_id"]), ("2026-09-06", event.pk))
        event.invite_only = True
        event.save()
        refused = self.post("/api/v1/gallery/albums/", {"competition_id": event.pk}, user=self.admin)
        self.assertEqual(refused.status_code, 422)
        self.assertIn("competition_id", refused.json()["detail"])

    def test_an_album_without_a_title_or_a_date_is_refused_naming_the_field(self):
        response = self.post("/api/v1/gallery/albums/", {"date": "2026-10-01"}, user=self.admin)
        self.assertEqual(response.status_code, 422)
        self.assertIn("title.ru", response.json()["detail"])
        response = self.post("/api/v1/gallery/albums/", {"title": {"ru": "X"}}, user=self.admin)
        self.assertIn("date", response.json()["detail"])
        response = self.post(
            "/api/v1/gallery/albums/", {"title": {"en": "x" * 201}, "date": "2026-10-01"}, user=self.admin
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("title.en", response.json()["detail"])

    def test_a_patch_changes_only_what_it_sends(self):
        response = self.patch(f"/api/v1/gallery/albums/{self.album.pk}", {"is_hidden": True}, user=self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.album.refresh_from_db()
        self.assertTrue(self.album.is_hidden)
        # The empty Kazakh title stays empty rather than taking the Russian one.
        self.assertEqual((self.album.title_ru, self.album.title_kk, self.album.title_en), ("Gonka", "", "The race"))
        self.patch(f"/api/v1/gallery/albums/{self.album.pk}", {"title": {"kk": "Zharys"}}, user=self.admin)
        self.album.refresh_from_db()
        self.assertEqual((self.album.title_ru, self.album.title_kk), ("", "Zharys"))

    def test_a_patch_links_and_unlinks_an_event(self):
        event = Competition.objects.create(title_ru="Race", date_start="2026-09-06", status=Competition.Status.APPROVED)
        self.patch(f"/api/v1/gallery/albums/{self.album.pk}", {"competition_id": event.pk}, user=self.admin)
        self.album.refresh_from_db()
        self.assertEqual(self.album.competition_id, event.pk)
        self.assertEqual(self.album.title_ru, "Gonka")  # a title given by hand wins
        self.patch(f"/api/v1/gallery/albums/{self.album.pk}", {"competition_id": None}, user=self.admin)
        self.album.refresh_from_db()
        self.assertIsNone(self.album.competition_id)

    def test_the_cover_is_one_of_the_albums_own_photos(self):
        first, second = self._photo(self.album), self._photo(self.album)
        response = self.patch(f"/api/v1/gallery/albums/{self.album.pk}", {"cover_photo_id": second.pk}, user=self.admin)
        self.assertEqual(response.json()["cover_photo_id"], second.pk)
        stranger = self._photo(self._album(title="Other"))
        refused = self.patch(
            f"/api/v1/gallery/albums/{self.album.pk}", {"cover_photo_id": stranger.pk}, user=self.admin
        )
        self.assertEqual(refused.status_code, 422)
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover_id, second.pk)
        cleared = self.patch(f"/api/v1/gallery/albums/{self.album.pk}", {"cover_photo_id": None}, user=self.admin)
        self.assertEqual(cleared.json()["cover_photo_id"], first.pk)  # the first photo stands in

    def test_uploads_keep_the_pictures_list_the_rest_and_give_a_new_album_its_cover(self):
        not_a_picture = SimpleUploadedFile("notes.jpg", b"not an image", content_type="image/jpeg")
        response = self._upload(self.album, _jpeg("a.jpg"), not_a_picture, _jpeg("b.jpg"))
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(len(body["photos"]), 2)
        self.assertEqual(len(body["failed"]), 1)
        self.assertTrue(body["failed"][0].startswith("notes.jpg: "))
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover_id, body["photos"][0]["id"])
        later = self._upload(self.album, _jpeg("c.jpg")).json()["photos"][0]
        self.assertGreater(later["sort_order"], body["photos"][1]["sort_order"])
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover_id, body["photos"][0]["id"])  # a picked cover stays

    def test_an_upload_with_nothing_usable_or_over_the_limits_is_refused(self):
        bad = SimpleUploadedFile("x.jpg", b"nope", content_type="image/jpeg")
        self.assertEqual(self._upload(self.album, bad).status_code, 422)
        with self.settings(GALLERY_MAX_FILES_PER_UPLOAD=1):
            response = self._upload(self.album, _jpeg("a.jpg"), _jpeg("b.jpg"))
        self.assertEqual(response.status_code, 422)
        self.assertIn("photos", response.json()["detail"])
        self.assertFalse(self.album.photos.exists())

    def test_a_caption_is_set_per_language_within_its_column(self):
        photo = self._photo(self.album)
        response = self.patch(
            f"/api/v1/gallery/photos/{photo.pk}", {"caption": {"ru": "Finish", "en": "The finish"}}, user=self.admin
        )
        self.assertEqual(response.status_code, 200, response.content)
        photo.refresh_from_db()
        self.assertEqual((photo.caption_ru, photo.caption_kk, photo.caption_en), ("Finish", "", "The finish"))
        too_long = self.patch(f"/api/v1/gallery/photos/{photo.pk}", {"caption": {"ru": "x" * 201}}, user=self.admin)
        self.assertEqual(too_long.status_code, 422)
        self.assertEqual(MAX_CAPTION_LENGTH, Photo._meta.get_field("caption").max_length)

    def test_deleting_a_photo_takes_its_files_and_the_next_one_becomes_the_cover(self):
        first, second = self._photo(self.album), self._photo(self.album)
        self.album.cover = first
        self.album.save()
        files = [first.image.path, first.thumbnail.path]
        self.assertEqual(self.delete(f"/api/v1/gallery/photos/{first.pk}", user=self.admin).status_code, 204)
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover_id, second.pk)
        self.assertFalse(any(Path(f).exists() for f in files))

    def test_deleting_an_album_takes_its_photos_and_files(self):
        photo = self._photo(self.album)
        path = Path(photo.image.path)
        self.assertEqual(self.delete(f"/api/v1/gallery/albums/{self.album.pk}", user=self.admin).status_code, 204)
        self.assertFalse(Album.objects.filter(pk=self.album.pk).exists())
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())
        self.assertFalse(path.exists())
        self.assertEqual(self.delete(f"/api/v1/gallery/albums/{self.album.pk}", user=self.admin).status_code, 404)
