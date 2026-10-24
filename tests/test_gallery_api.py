"""The gallery over the API (issue #365): readers see what the pages show them."""

import datetime
import uuid

from api.tests import ApiTestMixin
from calendar_app.models import Competition
from tests.test_gallery import GalleryTestCase


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
