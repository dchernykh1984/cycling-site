"""Translated gallery content, searchable event choices and albums with or without an event."""

import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from accounts.models import User
from calendar_app.models import Competition, Discipline, DisciplineCategory, EventType
from gallery.models import Album, Photo
from locations.models import add_location_child

CYRILLIC_FONDO = "\u0413\u0440\u0430\u043d \u0424\u043e\u043d\u0434\u043e"
DAY = datetime.date(2026, 10, 23)


class GalleryTranslationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="gallery.editor", role=User.Role.ADMIN)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_an_album_keeps_every_title_and_can_have_no_event(self):
        response = self.client.post(
            "/en/gallery/albums/new/",
            {"title_ru": "Album RU", "title_kk": "Album KK", "title_en": "Album EN", "date": DAY.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        album = Album.objects.get()
        self.assertEqual((album.title_ru, album.title_kk, album.title_en), ("Album RU", "Album KK", "Album EN"))
        self.assertIsNone(album.competition_id)
        for language, title in (("ru", "Album RU"), ("kk", "Album KK"), ("en", "Album EN")):
            with self.subTest(language=language):
                page = self.client.get(f"/{language}/gallery/albums/{album.pk}/")
                self.assertContains(page, title)
                self.assertNotContains(page, 'id="gallery-linked-event"')
                self.assertContains(self.client.get(f"/{language}/gallery/albums/"), title)
                self.assertContains(self.client.get(f"/{language}/gallery/"), title)

    def test_a_title_in_one_language_is_enough_and_falls_back_without_being_copied(self):
        self.client.post("/kk/gallery/albums/new/", {"title_en": "Only EN", "date": DAY.isoformat()})
        album = Album.objects.get()
        self.assertEqual(album.title_en, "Only EN")
        self.assertEqual(album.title_ru or "", "")
        self.assertEqual(album.title_kk or "", "")
        self.assertContains(self.client.get(f"/ru/gallery/albums/{album.pk}/"), "Only EN")

    def test_event_defaults_use_each_actual_translation_not_the_active_language(self):
        event = Competition.objects.create(
            title_ru="Event RU",
            title_kk="Event KK",
            title_en="Event EN",
            date_start=DAY,
            status=Competition.Status.APPROVED,
        )
        self.client.post("/kk/gallery/albums/new/", {"competition": event.pk, "title_en": "My EN"})
        album = Album.objects.get()
        self.assertEqual((album.title_ru, album.title_kk, album.title_en), ("Event RU", "Event KK", "My EN"))
        self.assertEqual(album.date, DAY)

    def test_missing_event_translations_stay_empty(self):
        event = Competition.objects.create(title_ru="RU only", date_start=DAY, status=Competition.Status.APPROVED)
        self.client.post("/en/gallery/albums/new/", {"competition": event.pk})
        album = Album.objects.get()
        self.assertEqual(album.title_ru, "RU only")
        self.assertEqual(album.title_kk or "", "")
        self.assertEqual(album.title_en or "", "")

    def test_an_edit_keeps_languages_separate_and_can_remove_the_event(self):
        event = Competition.objects.create(title_ru="Event", date_start=DAY, status=Competition.Status.APPROVED)
        album = Album.objects.create(title_ru="RU", title_en="Old EN", date=DAY, competition=event)
        response = self.client.post(
            f"/kk/gallery/albums/{album.pk}/edit/",
            {"competition": "", "title_ru": "RU", "title_kk": "KK", "title_en": "New EN", "date": DAY.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        album.refresh_from_db()
        self.assertIsNone(album.competition_id)
        self.assertEqual((album.title_ru, album.title_kk, album.title_en), ("RU", "KK", "New EN"))

    def test_an_oversized_event_title_does_not_turn_into_a_server_error(self):
        event = Competition.objects.create(title_ru="X" * 255, date_start=DAY, status=Competition.Status.APPROVED)
        response = self.client.post("/ru/gallery/albums/new/", {"competition": event.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn("title_ru", response.context["form"].errors)
        self.assertFalse(Album.objects.exists())

    def test_photo_captions_and_album_titles_follow_the_photo_page_language(self):
        album = Album.objects.create(title_ru="Album RU", title_kk="Album KK", title_en="Album EN", date=DAY)
        photo = Photo.objects.create(
            album=album,
            image="test/photo.jpg",
            thumbnail="test/thumb.jpg",
            caption_ru="Caption RU",
            caption_kk="Caption KK",
            caption_en="Caption EN",
        )
        for language in ("ru", "kk", "en"):
            page = self.client.get(f"/{language}/gallery/photos/{photo.pk}/")
            self.assertContains(page, f"Caption {language.upper()}")
            self.assertContains(page, f"Album {language.upper()}")

    def test_administration_exposes_all_translations(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from gallery.admin import AlbumAdmin, PhotoInline

        request = RequestFactory().get("/")
        request.user = self.admin
        album_fields = AlbumAdmin(Album, AdminSite()).get_form(request).base_fields
        photo_fields = PhotoInline(Album, AdminSite()).get_formset(request).form.base_fields
        self.assertTrue({"title_ru", "title_kk", "title_en"} <= set(album_fields))
        self.assertTrue({"caption_ru", "caption_kk", "caption_en"} <= set(photo_fields))


class GalleryEventSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="event.search.admin", role=User.Role.ADMIN)
        cls.event = Competition.objects.create(
            title_ru="Gran Fondo",
            title_kk="Fondo KK",
            title_en="Fondo EN",
            date_start=DAY,
            status=Competition.Status.APPROVED,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _search(self, query, language="ru"):
        return self.client.get(f"/{language}/gallery/events/", {"q": query})

    def test_cyrillic_finds_a_latin_name_in_every_page_language(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                response = self._search(CYRILLIC_FONDO, language)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.json()["results"]], [self.event.pk])
                self.assertIn("no-store", response.headers["Cache-Control"])

    def test_latin_finds_a_cyrillic_name(self):
        self.event.title_ru = CYRILLIC_FONDO
        self.event.title_kk = ""
        self.event.title_en = ""
        self.event.save()
        self.assertEqual(self._search("GRAN fondo").json()["results"][0]["id"], self.event.pk)

    def test_case_punctuation_mixed_scripts_and_year_are_searchable(self):
        for query in (" gRaN-FONDO ", CYRILLIC_FONDO.split()[0] + " fondo", "2026", "Fondo KK"):
            with self.subTest(query=query):
                self.assertEqual(self._search(query).json()["results"][0]["id"], self.event.pk)
        self.assertEqual(self._search("nonexistent").json()["results"], [])

    def test_choices_are_bounded_and_say_when_to_refine_the_query(self):
        Competition.objects.bulk_create(
            [
                Competition(title_ru=f"Another race {i}", date_start=DAY, status=Competition.Status.APPROVED)
                for i in range(25)
            ]
        )
        response = self._search("").json()
        self.assertEqual(len(response["results"]), 20)
        self.assertTrue(response["has_more"])

    def test_non_public_events_are_not_disclosed_even_to_the_picker_admin(self):
        for extra in (
            {"is_hidden": True},
            {"is_deleted": True},
            {"invite_only": True},
            {"status": Competition.Status.PENDING_APPROVAL},
            {"status": Competition.Status.REJECTED},
        ):
            fields = {"title_ru": "Secret Fondo", "date_start": DAY, "status": Competition.Status.APPROVED, **extra}
            Competition.objects.create(**fields)
        response = self._search("Fondo").json()
        self.assertEqual([row["id"] for row in response["results"]], [self.event.pk])

    def test_search_requires_gallery_editing_permission(self):
        self.client.logout()
        self.assertEqual(self._search("Fondo").status_code, 302)
        for role in (User.Role.PARTICIPANT, User.Role.ORGANIZER):
            user = User.objects.create_user(username=f"search.{role}", role=role)
            self.client.force_login(user)
            self.assertEqual(self._search("Fondo").status_code, 403)

    def test_overlong_search_and_wrong_method_are_refused(self):
        self.assertEqual(self._search("x" * 201).status_code, 400)
        self.assertEqual(self.client.post("/ru/gallery/events/").status_code, 405)

    def test_a_forged_event_does_not_create_an_album_or_crash_the_form(self):
        response = self.client.post(
            "/ru/gallery/albums/new/", {"competition": "invalid", "title_ru": "Album", "date": DAY.isoformat()}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("competition", response.context["form"].errors)
        self.assertFalse(Album.objects.exists())


class GalleryEventDetailsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="event.details.admin", role=User.Role.ADMIN)
        country = add_location_child(None, name_ru="Country RU", name_kk="Country KK", name_en="Country EN")
        region = add_location_child(country, name_ru="Region RU", name_kk="Region KK", name_en="Region EN")
        city = add_location_child(region, name_ru="City RU", name_kk="City KK", name_en="City EN")
        venue = add_location_child(city, name_ru="Venue RU", name_kk="Venue KK", name_en="Venue EN")
        category = DisciplineCategory.objects.create(name_ru="Cycling RU", name_kk="Cycling KK", name_en="Cycling EN")
        discipline = Discipline.objects.create(
            category=category, name_ru="Road RU", name_kk="Road KK", name_en="Road EN"
        )
        kind = EventType.objects.create(name_ru="Race RU", name_kk="Race KK", name_en="Race EN")
        cls.event = Competition.objects.create(
            title_ru="Event RU",
            title_kk="Event KK",
            title_en="Event EN",
            description_ru="LONG_DESCRIPTION_MUST_NOT_APPEAR",
            date_start=DAY,
            date_end=DAY + datetime.timedelta(days=2),
            location=venue,
            status=Competition.Status.APPROVED,
        )
        cls.event.disciplines.add(discipline)
        cls.event.event_types.add(kind)
        cls.album = Album.objects.create(title_ru="Album", date=DAY, competition=cls.event)

    def test_the_album_and_picker_show_localized_facts_but_no_event_description(self):
        self.client.force_login(self.admin)
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                response = self.client.get(f"/{language}/gallery/albums/{self.album.pk}/")
                self.assertContains(response, 'id="gallery-linked-event"')
                for prefix in ("Event", "City", "Venue", "Cycling", "Road", "Race"):
                    self.assertContains(response, f"{prefix} {language.upper()}")
                self.assertNotContains(response, "LONG_DESCRIPTION_MUST_NOT_APPEAR")
                choice = self.client.get(f"/{language}/gallery/events/", {"q": "Event"}).json()["results"][0]
                self.assertEqual(len(choice["details"]), 5)
                self.assertIn(f"City {language.upper()}", str(choice["details"]))

    def test_metadata_disappears_when_the_event_stops_being_public(self):
        self.event.is_hidden = True
        self.event.save(update_fields=["is_hidden"])
        self.client.logout()
        response = self.client.get(f"/ru/gallery/albums/{self.album.pk}/")
        self.assertNotContains(response, 'id="gallery-linked-event"')
        self.assertNotContains(response, "City RU")


class ExistingGalleryTextMigrationTests(TransactionTestCase):
    def test_existing_titles_and_captions_survive_without_invented_translations(self):
        old_target = [("gallery", "0002_photo_size_as_shown")]
        new_target = [("gallery", "0003_localized_album_titles_and_photo_captions")]
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(old_target)
            old_apps = executor.loader.project_state(old_target).apps
            album = old_apps.get_model("gallery", "Album").objects.create(title="Existing title", date=DAY)
            photo = old_apps.get_model("gallery", "Photo").objects.create(
                album_id=album.pk,
                caption="Existing caption",
                image="migration/photo.jpg",
                thumbnail="migration/thumb.jpg",
            )
            executor = MigrationExecutor(connection)
            executor.migrate(new_target)
            apps = executor.loader.project_state(new_target).apps
            migrated_album = apps.get_model("gallery", "Album").objects.get(pk=album.pk)
            migrated_photo = apps.get_model("gallery", "Photo").objects.get(pk=photo.pk)
            self.assertEqual(migrated_album.title_ru, "Existing title")
            self.assertEqual(migrated_photo.caption_ru, "Existing caption")
            self.assertIsNone(migrated_album.title_en)
            self.assertIsNone(migrated_album.title_kk)
            self.assertIsNone(migrated_photo.caption_en)
            self.assertIsNone(migrated_photo.caption_kk)
            migrated_album.title_ru = ""
            migrated_album.title_en = "New EN title"
            migrated_album.save(update_fields=["title_ru", "title_en"])
            migrated_photo.caption_ru = None
            migrated_photo.caption_en = "New EN caption"
            migrated_photo.save(update_fields=["caption_ru", "caption_en"])
            executor = MigrationExecutor(connection)
            executor.migrate(old_target)
            old_apps = executor.loader.project_state(old_target).apps
            self.assertEqual(old_apps.get_model("gallery", "Album").objects.get(pk=album.pk).title, "New EN title")
            self.assertEqual(old_apps.get_model("gallery", "Photo").objects.get(pk=photo.pk).caption, "New EN caption")
        finally:
            MigrationExecutor(connection).migrate(new_target)
