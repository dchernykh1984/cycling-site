"""Event photos from an indexed Dropbox folder (issue #349): the index check, the import, the bibs a
start list assigns, and the participants' own marks. No test reaches Dropbox: FakeAdapter stands in."""

import datetime
import hashlib
import json
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from typing import ClassVar
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from calendar_app.models import Competition
from event_photos import actions, bindings
from event_photos import index as index_module
from event_photos.models import (
    BibObservation,
    ExternalAlbum,
    IndexedPhoto,
    IssuedBib,
    IssuedBibEvent,
    PhotoDecision,
)
from registrations.models import CompetitionRegistration

EXAMPLE = Path(settings.BASE_DIR) / "specs" / "349-external-photo-albums" / "examples" / "photo-index.v1.json"
FOLDER = "https://www.dropbox.com/scl/fo/abc123/DEF456?rlkey=k&st=s"
MEDIA = tempfile.mkdtemp()


class FakeAdapter:
    files: ClassVar[dict[str, bytes]] = {}
    thumbnails_served = 0

    def read_file(self, folder_url, path):
        from event_photos.dropbox import DropboxError

        if path not in self.files:
            raise DropboxError("not-found")
        return self.files[path]

    def thumbnail(self, folder_url, path):
        FakeAdapter.thumbnails_served += 1
        return b"jpeg:" + path.encode()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _photo(n: int, bibs=(), *, content="v1", state="processed"):
    original = _sha(f"photo-{n}-{content}")
    return {
        "id": str(uuid.UUID(int=n + 1)),
        "original": {"path": f"IMG_{n:04d}.jpg", "sha256": original, "bytes": 1000 + n, "media_type": "image/jpeg"},
        "processing_state": state,
        "bibs": [
            {"value": b, "state": s, "method": m, **({"content_sha256": original} if m == "manual" else {})}
            for b, s, m in bibs
        ],
    }


ALBUM = uuid.UUID(int=999)


def _index(photos, *, revision=1, album=ALBUM, removed=(), complete=True) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "album_id": str(album),
            "revision": revision,
            "generated_at": "2026-10-26T00:00:00Z",
            "producer": {"name": "test", "version": "0"},
            "bib_normalization": "trim-nfc-exact-v1",
            "processing": {"inventory_complete": complete, "complete": complete, "total": len(photos), "processed": 0},
            "photos": photos,
            "removed_photo_ids": [str(uuid.UUID(int=n + 1)) for n in removed],
        }
    ).encode()


class AdapterTests(TestCase):
    @override_settings(DROPBOX_APP_KEY="k", DROPBOX_APP_SECRET="s", PHOTO_INDEX_MAX_BYTES=5_000_000)
    def test_an_oversized_index_is_abandoned_without_reading_the_rest(self):
        from event_photos.dropbox import DropboxAdapter, DropboxError

        served = []

        def chunks(size):
            for _ in range(200):  # 200 x 64 KB = 13 MB on offer, no Content-Length
                served.append(size)
                yield b"x" * size

        response = mock.MagicMock(status_code=200, headers={})
        response.iter_content.side_effect = chunks
        response.__enter__.return_value = response
        with mock.patch("event_photos.dropbox.requests.post", return_value=response) as post:
            with self.assertRaisesRegex(DropboxError, "too-large"):
                DropboxAdapter().read_file(FOLDER, "photo-index.v1.json")
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertLess(sum(served), 5_200_000)
        response.__exit__.assert_called_once()


class IndexCheckTests(TestCase):
    def _parse(self, raw):
        return index_module.parse(raw, hashlib.sha256(raw).hexdigest())

    def test_the_specification_example_passes(self):
        parsed = self._parse(EXAMPLE.read_bytes())
        self.assertEqual(parsed.photos[0].bibs[0].value, "00120")  # leading zeroes kept

    def test_a_bib_is_trimmed_but_otherwise_kept_as_written(self):
        parsed = self._parse(_index([_photo(1, [(" 07A ", "accepted", "ocr")])]))
        self.assertEqual(parsed.photos[0].bibs[0].value, "07A")

    def test_a_manual_mark_must_name_the_bytes_it_was_made_on(self):
        photo = _photo(1, [("12", "accepted", "manual")])
        photo["bibs"][0]["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(index_module.IndexValidationError, "content_sha256"):
            self._parse(_index([photo]))

    def test_an_appearance_match_cannot_be_accepted_by_the_producer(self):
        with self.assertRaisesRegex(index_module.IndexValidationError, "always a candidate"):
            self._parse(_index([_photo(1, [("12", "accepted", "appearance")])]))

    def test_paths_that_leave_the_folder_are_refused(self):
        for bad in ("../x.jpg", "/abs.jpg", "a//b.jpg", "https://evil/x.jpg", "a\\b.jpg"):
            photo = _photo(1)
            photo["original"]["path"] = bad
            with self.subTest(bad), self.assertRaisesRegex(index_module.IndexValidationError, "original.path"):
                self._parse(_index([photo]))

    def test_the_downloadable_example_passes_the_check(self):
        from event_photos.index import SAMPLE

        self.assertEqual(len(self._parse(SAMPLE.encode()).photos), 1)

    def test_a_provider_hash_is_not_a_sha256(self):
        photo = _photo(1)
        photo["original"]["sha256"] = "ABC"
        with self.assertRaisesRegex(index_module.IndexValidationError, "SHA-256"):
            self._parse(_index([photo]))

    @override_settings(PHOTO_INDEX_MAX_PHOTOS=2)
    def test_too_many_photos_names_the_limit(self):
        with self.assertRaisesRegex(index_module.IndexValidationError, "more than 2 photos"):
            self._parse(_index([_photo(n) for n in range(3)]))

    def test_a_successor_must_keep_or_tombstone_every_live_photo(self):
        live = {uuid.UUID(int=n + 1) for n in range(100)}
        partial = self._parse(_index([_photo(n) for n in range(50)], revision=2, complete=False))
        with self.assertRaisesRegex(index_module.IndexValidationError, "50 photo"):
            index_module.check_successor(partial, revision=1, sha256="x", live=live)
        tombstoned = self._parse(_index([_photo(n) for n in range(50)], revision=2, removed=range(50, 100)))
        self.assertTrue(index_module.check_successor(tombstoned, revision=1, sha256="x", live=live))

    def test_an_incomplete_scan_cannot_remove_a_published_photo(self):
        live = {uuid.UUID(int=n + 1) for n in range(2)}
        partial = self._parse(_index([_photo(0)], revision=2, removed=[1], complete=False))
        with self.assertRaisesRegex(index_module.IndexValidationError, "incomplete scan"):
            index_module.check_successor(partial, revision=1, sha256="x", live=live)

    def test_revisions_only_move_forward(self):
        parsed = self._parse(_index([_photo(1)], revision=3))
        with self.assertRaisesRegex(index_module.IndexValidationError, "older"):
            index_module.check_successor(parsed, revision=4, sha256="x", live=set())
        self.assertFalse(index_module.check_successor(parsed, revision=3, sha256=parsed.sha256, live=set()))
        with self.assertRaisesRegex(index_module.IndexValidationError, "different index"):
            index_module.check_successor(parsed, revision=3, sha256="other", live=set())


@override_settings(EVENT_PHOTOS_ADAPTER="tests.test_event_photos.FakeAdapter", MEDIA_ROOT=MEDIA)
class EventPhotosTestCase(TestCase):
    def setUp(self):
        FakeAdapter.files = {}
        FakeAdapter.thumbnails_served = 0
        self.race = Competition.objects.create(
            title_ru="Alatau XCO", date_start=datetime.date(2026, 10, 11), status=Competition.Status.APPROVED
        )
        self.album = ExternalAlbum.objects.create(competition=self.race, folder_url=FOLDER, title="Folder A")

    def _publish(self, raw, album=None):
        FakeAdapter.files[actions.INDEX_FILE] = raw
        return actions.import_album(album or self.album, None)

    def _registration(self, last="Ivanov"):
        return CompetitionRegistration.objects.create(
            competition=self.race, first_name="Ivan", last_name=last, birth_date=datetime.date(1990, 1, 1), gender="M"
        )

    def _bib(self, registration, bib):
        return IssuedBib.objects.create(competition=self.race, registration=registration, bib=bib)


class ImportTests(EventPhotosTestCase):
    def test_an_import_publishes_the_photos_and_their_bibs(self):
        self.assertTrue(self._publish(_index([_photo(1, [("12", "accepted", "ocr")]), _photo(2)])))
        self.album.refresh_from_db()
        self.assertEqual((self.album.photo_count, self.album.revision, self.album.last_error), (2, 1, ""))
        self.assertEqual(IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=2)).bibs.get().value, "12")

    def test_the_same_snapshot_twice_changes_nothing(self):
        raw = _index([_photo(1)])
        self._publish(raw)
        self.assertFalse(self._publish(raw))

    def test_an_incomplete_index_never_takes_photos_away(self):
        self._publish(_index([_photo(n) for n in range(100)]))
        with self.assertRaises(actions.ImportFailedError):
            self._publish(_index([_photo(n) for n in range(50)], revision=2, complete=False))
        self.album.refresh_from_db()
        self.assertEqual(IndexedPhoto.objects.filter(album=self.album, in_index=True).count(), 100)
        self.assertIn("missing without being listed", self.album.last_error)

    def test_a_removed_photo_keeps_its_marks_and_comes_back_with_them(self):
        reg = self._registration()
        self._publish(_index([_photo(1), _photo(2)]))
        photo = IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=3))  # _photo(2)
        actions.decide(reg, photo, PhotoDecision.State.ME, None)
        self._publish(_index([_photo(1)], revision=2, removed=[2]))
        photo.refresh_from_db()
        self.assertFalse(photo.in_index)
        self._publish(_index([_photo(1), _photo(2)], revision=3))
        photo.refresh_from_db()
        self.assertTrue(photo.in_index)
        self.assertEqual(PhotoDecision.objects.get(photo=photo).state, PhotoDecision.State.ME)

    def test_an_older_index_arriving_late_does_not_roll_the_album_back(self):
        newer, older = _index([_photo(1), _photo(2)], revision=3), _index([_photo(1)], revision=2)
        self._publish(newer)
        with self.assertRaises(actions.ImportFailedError):
            self._publish(older)
        self.album.refresh_from_db()
        self.assertEqual((self.album.revision, self.album.photo_count), (3, 2))

    def test_another_folder_cannot_take_over_a_connected_album(self):
        self._publish(_index([_photo(1)]))
        copy = ExternalAlbum.objects.create(competition=self.race, folder_url=FOLDER + "x", title="Copy")
        with self.assertRaisesRegex(actions.ImportFailedError, "already connected"):
            self._publish(_index([_photo(1)]), album=copy)

    def test_malformed_fields_are_refused_by_name_not_with_a_server_error(self):
        self._publish(_index([_photo(1)]))
        cases = {
            "media_type": lambda p: p["original"].__setitem__("media_type", []),
            "processing_state": lambda p: p.__setitem__("processing_state", []),
            "bytes": lambda p: p["original"].__setitem__("bytes", 2**100),
            "NUL": lambda p: p["original"].__setitem__("view_url", "https://www.dropbox.com/scl/fi/a\x00b/x.jpg"),
        }
        for where, spoil in cases.items():
            photo = _photo(1)
            spoil(photo)
            with self.subTest(where), self.assertRaisesRegex(actions.ImportFailedError, where):
                self._publish(_index([photo], revision=2))
            self.album.refresh_from_db()
            self.assertIn(where, self.album.last_error)
            self.assertEqual(self.album.revision, 1)

    def test_a_missing_index_is_reported_and_keeps_the_last_publication(self):
        self._publish(_index([_photo(1)]))
        FakeAdapter.files = {}
        with self.assertRaises(actions.ImportFailedError):
            actions.import_album(self.album, None)
        self.assertEqual(IndexedPhoto.objects.filter(album=self.album).count(), 1)


class ThumbnailTests(EventPhotosTestCase):
    def test_a_thumbnail_is_fetched_once_and_kept_where_media_does_not_serve_it(self):
        self._publish(_index([_photo(1)]))
        photo = IndexedPhoto.objects.get()
        path = actions.thumbnail_path(photo)
        photo.refresh_from_db()
        actions.thumbnail_path(photo)
        self.assertEqual(FakeAdapter.thumbnails_served, 1)
        self.assertIn("/private/", str(path))
        relative = path.relative_to(MEDIA)
        self.assertEqual(self.client.get(f"/media/{relative}").status_code, 404)
        self.assertEqual(self.client.get(f"/media/x/../{relative}").status_code, 404)

    def test_new_bytes_make_a_new_thumbnail(self):
        self._publish(_index([_photo(1)]))
        old = actions.thumbnail_path(IndexedPhoto.objects.get())
        with self.captureOnCommitCallbacks(execute=True):
            self._publish(_index([_photo(1, content="v2")], revision=2))
        photo = IndexedPhoto.objects.get()
        self.assertEqual(photo.thumb_file, "")
        self.assertFalse(old.exists())
        self.assertNotEqual(actions.thumbnail_path(photo), old)


class StartLineTests(TestCase):
    def test_lines_are_read_as_the_contract_says(self):
        cases = {
            "120#Ivanov#M40#3#1#1984#T#C##0 00:00:00.000#": ((("120",), (), False)),
            "120#Ivanov#M40#3#1#1984#T#C##0 00:00:00.000#r1234#": ((("120",), (1234,), True)),
            "120#Ivanov#M40#3#1#1984#T#C##0 00:00:00.000##": ((("120",), (), True)),
            "15#Kim / Lee#Relay#3#1#1990#T#C##0 00:00:00.000#r21,r17,x9,r21#": ((("15",), (21, 17), True)),
            "12#Team#Relay#3#3#1990#T#C##0 00:00:00.000#r5#": ((("12", "13", "14"), (5,), True)),
            "NOT_PAID#Ivanov#M40#3#1#1984#T#C##0 00:00:00.000#r9#": (((), (9,), True)),
        }
        for line, (bibs, refs, present) in cases.items():
            parsed, _ = bindings.parse_line(line, max_stages=20)
            self.assertEqual((parsed.bibs, parsed.refs, parsed.refs_present), (bibs, refs, present), line)

    def test_a_huge_stage_count_is_not_expanded(self):
        parsed, warning = bindings.parse_line("120#X#G#1#1000000000#1#T#C##0#r1#", max_stages=20)
        self.assertEqual(parsed.bibs, ("120",))
        self.assertIn("over the limit", warning)

    def test_conflicts_review_and_unlinking(self):
        uploads = [
            ("a", 1, ["1#A#G#1#1#1#T#C##0#r1#", "2#B#G#1#1#1#T#C##0#r2#", "3#C#G#1#1#1#T#C##0#r3#"]),
            ("b", 1, ["4#A#G#1#1#1#T#C##0#r1#", "5#D#G#1#1#1#T#C##0#", "6#E#G#1#1#1#T#C##0##"]),
        ]
        previous = {(5, "5"): "active", (6, "6"): "active"}
        result = bindings.compute(uploads, {1, 2, 3, 5, 6}, previous)
        self.assertEqual(result.assignments[(1, "1")][0], "conflict")  # one registration, two bibs
        self.assertEqual(result.assignments[(2, "2")][0], "active")
        self.assertEqual(result.assignments[(5, "5")][0], "review")  # an old program dropped the field
        self.assertNotIn((6, "6"), result.assignments)  # the referee unlinked it

    def test_a_restored_binding_still_conflicts_with_a_new_line(self):
        uploads = [("a", 2, ["12#Old#G#1#1#1#T#C##0#", "12#New#G#1#1#1#T#C##0#r2#"])]
        result = bindings.compute(uploads, {1, 2}, {(1, "12")})
        self.assertEqual(result.assignments[(1, "12")][0], "conflict")
        self.assertEqual(result.assignments[(2, "12")][0], "conflict")

    def test_a_rejected_registration_is_not_restored(self):
        uploads = [("a", 2, ["12#Old#G#1#1#1#T#C##0#"])]
        self.assertEqual(bindings.compute(uploads, set(), {(1, "12")}).assignments, {})


class StartListUploadTests(EventPhotosTestCase):
    def test_an_upload_assigns_bibs_and_keeps_their_history(self):
        reg = self._registration()
        body = {
            "competition_token": str(self.race.upload_token),
            "device_id": "dev",
            "items": [f"120#Ivanov#M40#3#1#1990#T#C##0 00:00:00.000#r{reg.pk}#", "121#Hand#M40#3#1#1990#T#C##0#"],
            "client_revision": 1,
        }
        response = self.client.post("/api/v1/start-list/", body, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(IssuedBib.objects.values_list("registration_id", "bib", "state")), [(reg.pk, "120", "active")]
        )
        body.update(items=["120#Ivanov#M40#3#1#1990#T#C##0 00:00:00.000##"], client_revision=2)
        self.client.post("/api/v1/start-list/", body, content_type="application/json")
        self.assertFalse(IssuedBib.objects.exists())
        self.assertEqual(
            list(IssuedBibEvent.objects.order_by("pk").values_list("change", flat=True)), ["assigned", "withdrawn"]
        )

    def _upload(self, items, revision, device="dev"):
        body = {
            "competition_token": str(self.race.upload_token),
            "device_id": device,
            "items": items,
            "client_revision": revision,
        }
        return self.client.post("/api/v1/start-list/", body, content_type="application/json")

    def test_too_many_assignments_keep_the_previous_ones(self):
        reg = self._registration()
        self._upload([f"120#A#G#1#1#1#T#C##0#r{reg.pk}#"], 1)
        with mock.patch.object(bindings, "_MAX_ASSIGNMENTS", 2):
            self._upload([f"120#A#G#1#3#1#T#C##0#r{reg.pk}#"], 2)
        self.assertEqual(list(IssuedBib.objects.values_list("bib", flat=True)), ["120"])
        warnings = self.race.start_list_diagnostics.warnings
        self.assertIn("previous ones are kept", warnings[0])

    def test_a_resend_updates_the_source_and_conflicts_are_explained(self):
        reg = self._registration()
        self._upload([f"120#A#G#1#1#1#T#C##0#r{reg.pk}#"], 1)
        self._upload([f"120#A#G#1#1#1#T#C##0#r{reg.pk}#"], 2)
        self.assertEqual(IssuedBib.objects.get().client_revision, 2)
        self._upload([f"121#A#G#1#1#1#T#C##0#r{reg.pk}#"], 1, device="other")
        self.assertEqual(set(IssuedBib.objects.values_list("state", flat=True)), {"conflict"})
        self.assertTrue(any("conflict" in w for w in self.race.start_list_diagnostics.warnings))


class MatchTests(EventPhotosTestCase):
    def setUp(self):
        super().setUp()
        self._publish(
            _index(
                [
                    _photo(1, [("12", "accepted", "ocr")]),
                    _photo(2, [("12", "candidate", "appearance")]),
                    _photo(3, [("99", "accepted", "ocr")]),
                    _photo(4),
                ]
            )
        )
        self.photos = {p.photo_uuid.int - 1: p for p in IndexedPhoto.objects.all()}

    def test_a_registration_album_holds_its_matches_and_its_own_marks(self):
        reg = self._registration()
        self._bib(reg, "12")
        actions.decide(reg, self.photos[4], PhotoDecision.State.ME, None)
        actions.decide(reg, self.photos[2], PhotoDecision.State.NOT_ME, None)
        shown = {p.photo_uuid.int - 1: p.confirmed for p in actions.registration_photos(reg)}
        self.assertEqual(shown, {1: True, 4: True})

    def test_a_team_mates_not_me_does_not_hide_the_photo_from_the_bib_search(self):
        first, second = self._registration("A"), self._registration("B")
        self._bib(first, "12")
        self._bib(second, "12")
        actions.decide(first, self.photos[1], PhotoDecision.State.NOT_ME, None)
        self.assertEqual([p.photo_uuid.int - 1 for p in actions.bib_photos(self.race, "12")], [1])
        self.assertEqual([p.photo_uuid.int - 1 for p in actions.registration_photos(second)], [1, 2])
        actions.decide(second, self.photos[1], PhotoDecision.State.NOT_ME, None)
        self.assertEqual(list(actions.bib_photos(self.race, "12")), [])

    def test_a_mark_counts_only_for_the_markers_own_bib(self):
        reg = self._registration()
        self._bib(reg, "12")
        photo = IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=2))
        BibObservation.objects.create(photo=photo, value="7", state="accepted", method="manual")
        actions.decide(reg, photo, PhotoDecision.State.ME, None)
        stats = actions.mark_stats(self.album)
        self.assertEqual(stats["totals"]["confirmed"], 1)
        self.assertEqual(stats["by_method"], [{"method": "ocr", "confirmed": 1, "rejected": 0}])
        self.assertEqual(stats["totals"]["unchecked"], 2)  # photos 2 and 3 carry bibs nobody marked

    def test_a_bib_in_conflict_gives_nobody_photos(self):
        reg = self._registration()
        IssuedBib.objects.create(competition=self.race, registration=reg, bib="12", state=IssuedBib.State.CONFLICT)
        self.assertEqual(list(actions.registration_photos(reg)), [])


class DecisionTests(EventPhotosTestCase):
    def setUp(self):
        super().setUp()
        self._publish(_index([_photo(1)]))
        self.photo = IndexedPhoto.objects.get()
        self.reg = self._registration()

    def _state(self):
        return PhotoDecision.objects.get(registration=self.reg, photo=self.photo).state

    def test_me_then_not_me_then_undo_brings_the_check_back(self):
        actions.decide(self.reg, self.photo, "me", None)
        event = actions.decide(self.reg, self.photo, "not_me", None)
        actions.undo(self.reg, event.pk, None)
        self.assertEqual(self._state(), "me")

    def test_undo_of_a_first_cross_leaves_no_mark(self):
        event = actions.decide(self.reg, self.photo, "not_me", None)
        actions.undo(self.reg, event.pk, None)
        self.assertEqual(self._state(), "")

    def test_a_cross_is_final_and_repeating_it_changes_nothing(self):
        actions.decide(self.reg, self.photo, "not_me", None)
        self.assertIsNone(actions.decide(self.reg, self.photo, "not_me", None))
        with self.assertRaises(actions.DecisionRefusedError):
            actions.decide(self.reg, self.photo, "me", None)

    def test_a_late_or_repeated_undo_is_refused(self):
        event = actions.decide(self.reg, self.photo, "not_me", None)
        later = timezone.now() + timedelta(seconds=settings.PHOTO_DECISION_UNDO_SECONDS + 1)
        with (
            mock.patch("django.utils.timezone.now", return_value=later),
            self.assertRaises(actions.DecisionRefusedError),
        ):
            actions.undo(self.reg, event.pk, None)
        actions.undo(self.reg, event.pk, None)
        with self.assertRaises(actions.DecisionRefusedError):
            actions.undo(self.reg, event.pk, None)

    def test_an_undo_cannot_revert_an_older_change(self):
        first = actions.decide(self.reg, self.photo, "me", None)
        actions.decide(self.reg, self.photo, "not_me", None)
        with self.assertRaisesRegex(actions.DecisionRefusedError, "newer"):
            actions.undo(self.reg, first.pk, None)


class PageAndApiTests(EventPhotosTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import User

        self.athlete = User.objects.create_user(username="a@x.kz", email="a@x.kz", password="pw", role="participant")
        self.stranger = User.objects.create_user(username="s@x.kz", email="s@x.kz", password="pw", role="participant")
        self.organizer = User.objects.create_user(username="o@x.kz", email="o@x.kz", password="pw", role="organizer")
        self.race.submitted_by = self.organizer
        self.race.save(update_fields=["submitted_by"])
        self.reg = self._registration()
        self.reg.user = self.athlete
        self.reg.save(update_fields=["user"])
        self._bib(self.reg, "12")
        self._publish(_index([_photo(1, [("12", "accepted", "ocr")]), _photo(2, [("12", "candidate", "ocr")])]))
        self.photo = IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=2))

    def _url(self, name, *args):
        from django.urls import reverse

        return reverse(f"event_photos:{name}", args=[self.race.pk, *args])

    def test_the_athlete_sees_and_marks_their_album_and_others_do_not(self):
        self.client.force_login(self.athlete)
        page = self.client.get(self._url("registration", self.reg.pk))
        self.assertContains(page, "&#10003;")
        self.assertContains(page, "preview=IMG_0001.jpg")
        response = self.client.post(self._url("decide", self.reg.pk, self.photo.pk), {"state": "not_me"})
        self.assertIn("?undo=", response["Location"])
        self.assertEqual(PhotoDecision.objects.get().state, "not_me")
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self._url("registration", self.reg.pk)).status_code, 404)
        self.assertEqual(
            self.client.post(self._url("decide", self.reg.pk, self.photo.pk), {"state": "me"}).status_code, 404
        )

    def test_the_organizer_sees_the_album_but_does_not_mark_it(self):
        self.client.force_login(self.organizer)
        page = self.client.get(self._url("registration", self.reg.pk))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "&#10007;")

    def test_a_thumbnail_follows_the_albums_visibility_and_is_not_cached_publicly(self):
        url = self._url("thumb", self.photo.pk, self.photo.source_sha256[:16])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, max-age=3600")
        self.album.is_hidden = True
        self.album.save(update_fields=["is_hidden"])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.race.is_hidden = True
        self.race.save(update_fields=["is_hidden"])
        self.assertEqual(self.client.get(self._url("event")).status_code, 404)

    def test_event_search_finds_the_bib_and_the_event_page_links_my_photos(self):
        self.assertContains(self.client.get(self._url("event") + "?bib=12"), "IMG_0001.jpg")
        self.client.force_login(self.athlete)
        self.assertContains(self.client.get(self.race.get_absolute_url()), self._url("registration", self.reg.pk))

    def test_only_the_creator_or_an_admin_manages_albums(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self._url("manage")).status_code, 404)
        self.client.force_login(self.organizer)
        page = self.client.get(self._url("manage"))
        self.assertContains(page, "Folder A")
        self.assertContains(page, "photos-guide/")
        bad = self.client.post(self._url("manage"), {"folder_url": "https://drive.google.com/x", "title_ru": "X"})
        self.assertContains(bad, "Dropbox")

    def test_a_hidden_photo_leaves_search_albums_and_thumbnails_and_stays_hidden(self):
        photo1 = IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=2))
        self.client.force_login(self.organizer)
        self.client.post(self._url("photo_action", photo1.pk), {"action": "hide"})
        self.assertContains(self.client.get(self._url("album", self.album.pk)), 'value="show"')
        self.client.force_login(self.athlete)
        self.assertNotContains(self.client.get(self._url("event") + "?bib=12"), "IMG_0001.jpg")
        self.assertNotIn(photo1, list(actions.registration_photos(self.reg)))
        thumb = self._url("thumb", photo1.pk, photo1.source_sha256[:16])
        self.assertEqual(self.client.get(thumb).status_code, 404)
        self._publish(_index([_photo(1, [("12", "accepted", "ocr")]), _photo(2)], revision=2))
        photo1.refresh_from_db()
        self.assertTrue(photo1.is_hidden)
        self.organizer.api_token = uuid.uuid4()
        self.organizer.save(update_fields=["api_token"])
        shown = self.client.post(
            f"/api/v1/event-photos/photos/{photo1.pk}/show", HTTP_AUTHORIZATION=f"Bearer {self.organizer.api_token}"
        )
        self.assertEqual(shown.status_code, 204)
        photo1.refresh_from_db()
        self.assertFalse(photo1.is_hidden)

    def test_a_failed_first_import_is_reported_to_the_manager_only(self):
        self.organizer.api_token = uuid.uuid4()
        self.organizer.save(update_fields=["api_token"])
        FakeAdapter.files = {}
        created = self.client.post(
            f"/api/v1/event-photos/competitions/{self.race.pk}/albums",
            {"folder_url": FOLDER + "2", "title_ru": "B"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.organizer.api_token}",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual((created.json()["import_state"], created.json()["last_error"]), ("failed", "not-found"))
        public = self.client.get(f"/api/v1/event-photos/competitions/{self.race.pk}/albums").json()
        self.assertEqual({a["last_error"] for a in public}, {None})

    def test_profile_cards_follow_event_visibility_and_tell_registrations_apart(self):
        from django.urls import reverse

        second = self._registration()  # the same person entered for another distance
        second.user = self.athlete
        second.save(update_fields=["user"])
        self.client.force_login(self.athlete)
        profile = self.client.get(reverse("account_profile"))
        self.assertContains(profile, self._url("registration", self.reg.pk))
        self.assertContains(profile, self._url("registration", second.pk))
        self.assertContains(profile, "12")  # the first card names its bib
        self.assertEqual(actions.registration_summary(second)["state"], "no-bib")
        self.assertEqual(actions.registration_summary(self.reg)["count"], 2)
        self.race.is_hidden = True
        self.race.save(update_fields=["is_hidden"])
        self.assertNotContains(self.client.get(reverse("account_profile")), self._url("registration", self.reg.pk))

    def test_curated_gallery_albums_count_as_the_events_photos(self):
        from gallery.models import Album

        Album.objects.create(title="Best shots", date=self.race.date_start, competition=self.race)
        self.album.delete()
        self.assertContains(self.client.get(self.race.get_absolute_url()), self._url("event"))
        self.assertContains(self.client.get(self._url("event")), "Best shots")

    def test_a_big_original_without_preview_gets_a_placeholder_and_a_note_for_the_organizer(self):
        big = _photo(3, [("12", "accepted", "ocr")])
        big["original"]["bytes"] = 25 * 1024 * 1024
        self._publish(
            _index([_photo(1, [("12", "accepted", "ocr")]), _photo(2, [("12", "candidate", "ocr")]), big], revision=2)
        )
        photo = IndexedPhoto.objects.get(photo_uuid=uuid.UUID(int=4))
        page = self.client.get(self._url("event") + "?bib=12")
        self.assertNotContains(page, self._url("thumb", photo.pk, photo.source_sha256[:16]))
        self.assertContains(page, "preview=IMG_0003.jpg")  # still opens in Dropbox
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(self._url("manage")), "IMG_0003.jpg")
        served = FakeAdapter.thumbnails_served
        self.assertEqual(self.client.get(self._url("thumb", photo.pk, "x")).status_code, 404)
        self.assertEqual(FakeAdapter.thumbnails_served, served)  # Dropbox is not even asked

    @override_settings(PHOTO_INDEX_MAX_PHOTOS=1234)
    def test_the_guide_states_the_real_limits_in_every_language(self):
        from django.urls import reverse
        from django.utils.translation import override as translation_override

        for lang in ("ru", "kk", "en"):
            with translation_override(lang):
                url = reverse("event_photos:guide")
            self.assertContains(self.client.get(url), "1234")
        self.client.force_login(self.organizer)
        manage = self.client.get(self._url("manage"))
        self.assertContains(manage, "1234")
        self.assertContains(manage, "photo-index.v1.json")

    def test_the_creator_manages_albums_whatever_their_role(self):
        self.race.submitted_by = self.athlete  # a participant who created the event
        self.race.save(update_fields=["submitted_by"])
        self.client.force_login(self.athlete)
        self.assertEqual(self.client.get(self._url("manage")).status_code, 200)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self._url("manage")).status_code, 404)

    def test_the_api_follows_the_same_rules(self):
        self.athlete.api_token = uuid.uuid4()
        self.athlete.save(update_fields=["api_token"])
        self.stranger.api_token = uuid.uuid4()
        self.stranger.save(update_fields=["api_token"])
        mine = {"HTTP_AUTHORIZATION": f"Bearer {self.athlete.api_token}"}
        theirs = {"HTTP_AUTHORIZATION": f"Bearer {self.stranger.api_token}"}
        base = "/api/v1/event-photos"
        photos = self.client.get(f"{base}/registrations/{self.reg.pk}/photos", **mine).json()
        self.assertEqual(photos["count"], 2)
        self.assertEqual(self.client.get(f"{base}/registrations/{self.reg.pk}/photos", **theirs).status_code, 404)
        decided = self.client.post(
            f"{base}/registrations/{self.reg.pk}/photos/{self.photo.pk}/decision",
            {"state": "not_me"},
            content_type="application/json",
            **mine,
        ).json()
        undone = self.client.post(
            f"{base}/registrations/{self.reg.pk}/undo",
            {"event_id": decided["event_id"]},
            content_type="application/json",
            **mine,
        )
        self.assertEqual(undone.status_code, 204)
        self.assertEqual(self.client.get(f"{base}/competitions/{self.race.pk}/photos?bib=12").json()["count"], 1)
        self.assertEqual(self.client.get(f"{base}/albums/{self.album.pk}/stats", **mine).status_code, 404)

    def test_an_api_client_gets_thumbnails_of_an_invite_only_event_with_its_token(self):
        self.race.invite_only = True
        self.race.save(update_fields=["invite_only"])
        self.athlete.api_token = uuid.uuid4()
        self.athlete.save(update_fields=["api_token"])
        mine = {"HTTP_AUTHORIZATION": f"Bearer {self.athlete.api_token}"}
        photos = self.client.get(f"/api/v1/event-photos/registrations/{self.reg.pk}/photos", **mine).json()
        thumb = photos["photos"][0]["thumbnail_url"]
        self.assertEqual(self.client.get(thumb, **mine).status_code, 200)
        self.assertEqual(self.client.get(thumb).status_code, 404)  # no token, not invited

    def test_start_list_problems_reach_the_organizer_and_explain_a_conflict(self):
        from event_photos.models import StartListDiagnostics

        StartListDiagnostics.objects.create(competition=self.race, warnings=["bib 12: r9 is in conflict"])
        IssuedBib.objects.filter(registration=self.reg).update(state=IssuedBib.State.CONFLICT)
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(self._url("manage")), "bib 12: r9 is in conflict")
        self.organizer.api_token = uuid.uuid4()
        self.organizer.save(update_fields=["api_token"])
        api = self.client.get(
            f"/api/v1/event-photos/competitions/{self.race.pk}/start-list-diagnostics",
            HTTP_AUTHORIZATION=f"Bearer {self.organizer.api_token}",
        )
        self.assertEqual(api.json(), ["bib 12: r9 is in conflict"])
        self.client.force_login(self.athlete)
        page = self.client.get(self._url("registration", self.reg.pk).replace("/ru/", "/en/", 1))
        self.assertContains(page, "organizer is sorting it out")

    def test_a_bad_index_on_refresh_is_a_422_with_the_field_named(self):
        self.organizer.api_token = uuid.uuid4()
        self.organizer.save(update_fields=["api_token"])
        photo = _photo(1)
        photo["processing_state"] = []
        FakeAdapter.files[actions.INDEX_FILE] = _index([photo], revision=2)
        response = self.client.post(
            f"/api/v1/event-photos/albums/{self.album.pk}/refresh",
            HTTP_AUTHORIZATION=f"Bearer {self.organizer.api_token}",
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("processing_state", response.json()["detail"])
