"""Protocol sections (issue #452): an event's protocols under headings of their own, the timing software
publishing into one by its number, and the organizer adding, renaming and deleting them on the site and
through the API."""

import json
from http import HTTPStatus

from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.translation import gettext, override

from accounts.models import User
from protocols import sections
from protocols.models import Protocol, ProtocolSection
from registrations.tests import make_competition, make_user
from tests.test_protocol_upload import _html, _MediaMixin, _stored_files
from tests.test_virtual_members import _bearer

UPLOAD = "/api/v1/protocols/upload/"
DELETE = "/api/v1/protocols/delete/"
FINALS = {"ru": "Protokoly finalov", "kk": "Finaldyq hattamalar", "en": "Finals"}


def _api(competition, number=None) -> str:
    tail = "" if number is None else f"/{number}"
    return f"/api/v1/protocols/competitions/{competition.pk}/sections{tail}"


class _Event(_MediaMixin):
    def setUp(self):
        self._use_temp_media()
        self.author = make_user("author", role=User.Role.ORGANIZER)
        self.competition = make_competition(title="Race", title_en="Race", submitted_by=self.author)
        self.token = str(self.competition.upload_token)

    def _upload(self, protocol_type="absolute", text="results", **extra):
        data = {"competition_token": self.token, "protocol_type": protocol_type, "html_file": _html(text), **extra}
        with self.captureOnCommitCallbacks(execute=True):
            return Client().post(UPLOAD, data)

    def _delete(self, protocol_type="absolute", **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return Client().post(DELETE, {"competition_token": self.token, "protocol_type": protocol_type, **extra})


class PublishingIntoSectionsTest(_Event, TestCase):
    def test_software_that_names_no_section_publishes_into_the_first_as_before(self):
        self.assertEqual(self._upload(text="one").status_code, HTTPStatus.OK)
        self.assertEqual(self._upload(text="two").status_code, HTTPStatus.OK)
        protocol = Protocol.objects.get()
        self.assertEqual(protocol.section, sections.FIRST)
        self.assertIn(b"two", protocol.html_file.read())

    def test_a_protocol_published_into_a_section_leaves_the_first_sections_protocol_of_its_type(self):
        number = sections.add(self.competition, FINALS).number
        self._upload(text="qualification")
        self.assertEqual(self._upload(text="finals", section=number).status_code, HTTPStatus.OK)
        by_section = {p.section: p.html_file.read() for p in Protocol.objects.all()}
        self.assertIn(b"qualification", by_section[sections.FIRST])
        self.assertIn(b"finals", by_section[number])

    def test_a_section_the_event_does_not_have_is_refused_and_nothing_is_kept(self):
        deleted = sections.add(self.competition, FINALS).number
        sections.delete(self.competition, deleted)
        for number in (deleted, deleted + 1):
            with self.subTest(number=number):
                response = self._upload(section=number)
                self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
                self.assertIn(f"no protocol section {number}", response.json()["detail"])
        self.assertFalse(Protocol.objects.exists())
        self.assertEqual(_stored_files(self.media_root), set())

    def test_a_number_that_cannot_be_a_section_is_refused(self):
        for number in (0, -1, sections.LAST + 1):
            with self.subTest(number=number):
                self.assertEqual(self._upload(section=number).status_code, HTTPStatus.BAD_REQUEST)
                self.assertEqual(self._delete(section=number).status_code, HTTPStatus.BAD_REQUEST)

    def test_a_delete_removes_the_protocol_of_its_own_section_only(self):
        number = sections.add(self.competition, FINALS).number
        self._upload()
        self._upload(section=number)
        response = self._delete(section=number)
        self.assertEqual(response.json(), {"deleted": True})
        self.assertEqual(list(Protocol.objects.values_list("section", flat=True)), [sections.FIRST])
        self.assertEqual(self._delete(section=number + 1).status_code, HTTPStatus.BAD_REQUEST)


class SectionRulesTest(_Event, TestCase):
    def test_a_section_gets_a_number_the_event_never_had(self):
        self.assertEqual(sections.add(self.competition, FINALS).number, 2)
        self.assertEqual(sections.add(self.competition, FINALS).number, 3)
        sections.delete(self.competition, 3)
        self.assertEqual(sections.add(self.competition, FINALS).number, 4)

    def test_a_section_holding_protocols_stays(self):
        number = sections.add(self.competition, FINALS).number
        self._upload(section=number)
        with self.assertRaises(sections.SectionRefusedError):
            sections.delete(self.competition, number)
        self.assertFalse(ProtocolSection.objects.get(number=number).is_deleted)

    def test_the_first_section_is_renamed_and_never_deleted(self):
        with self.assertRaises(sections.SectionRefusedError):
            sections.delete(self.competition, sections.FIRST)
        sections.rename(self.competition, sections.FIRST, FINALS)
        with override("en"):
            self.assertEqual(sections.listing(self.competition)[0]["name"], "Finals")

    def test_a_deleted_section_cannot_be_renamed(self):
        number = sections.add(self.competition, FINALS).number
        sections.delete(self.competition, number)
        with self.assertRaises(ProtocolSection.DoesNotExist):
            sections.rename(self.competition, number, FINALS)

    def test_a_protocol_saved_by_code_that_knows_no_sections_lands_in_the_first(self):
        # As the release still serving during a deploy saves one, after this one has migrated
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO protocols_protocol (competition_id, protocol_type, html_file, is_live, stage_label,"
                " file_hash, last_updated) VALUES (%s, 'absolute', '', true, '', '', now())",
                [self.competition.pk],
            )
        self.assertEqual(Protocol.objects.get().section, sections.FIRST)


class EventPageTest(_Event, TestCase):
    def test_each_section_with_protocols_is_shown_under_its_name_in_its_order(self):
        empty = sections.add(self.competition, {"ru": "Pusto", "kk": "Bos", "en": "Empty"}).number
        finals = sections.add(self.competition, FINALS).number
        self._upload("group", section=finals)
        self._upload("absolute")
        for language in ("ru", "en"):
            with self.subTest(language=language), override(language):
                page = self.client.get(f"/{language}/calendar/{self.competition.pk}/").content.decode()
                first = page.index(gettext("Protocols"), page.index('id="protocol-section-1"'))
                self.assertLess(first, page.index(FINALS[language]))
                self.assertNotIn(f'id="protocol-section-{empty}"', page)
                self.assertIn(f'id="protocol-section-{finals}"', page)

    def test_a_protocols_page_names_its_section(self):
        number = sections.add(self.competition, FINALS).number
        self._upload(section=number)
        protocol = Protocol.objects.get()
        page = self.client.get(f"/en/protocols/{protocol.pk}/").content.decode()
        self.assertIn(f"#protocol-section-{number}", page)
        self.assertIn("Race \u2014 Finals \u2014 Absolute results", page)


class SectionsPageTest(_Event, TestCase):
    def _page(self):
        return reverse("protocol_sections", args=[self.competition.pk])

    def _post(self, **data):
        return self.client.post(self._page(), data, follow=True)

    def test_the_organizer_adds_renames_and_deletes_a_section(self):
        self.client.force_login(self.author)
        self._post(action="add", **{f"new-{code}": value for code, value in FINALS.items()})
        section = ProtocolSection.objects.get(number=2)
        self.assertEqual(section.name_en, "Finals")
        self._post(action="rename", number=2, **{"section-2-ru": "R", "section-2-kk": "K", "section-2-en": "E"})
        section.refresh_from_db()
        self.assertEqual((section.name_ru, section.name_kk, section.name_en), ("R", "K", "E"))
        self._post(action="delete", number=2)
        section.refresh_from_db()
        self.assertTrue(section.is_deleted)

    def test_each_button_says_which_section_it_acts_on(self):
        sections.add(self.competition, FINALS)
        self.client.force_login(self.author)
        with override("en"):
            page = self.client.get(f"/en/protocols/event/{self.competition.pk}/sections/").content.decode()
        for label in ("Save section 1", "Save section 2", "Delete section 2"):
            self.assertIn(label, page)
        self.assertNotIn("Delete section 1", page)

    def test_a_name_left_out_in_a_language_is_asked_for(self):
        self.client.force_login(self.author)
        response = self._post(action="add", **{"new-ru": "R", "new-kk": "", "new-en": "E"})
        self.assertContains(response, "is-invalid")
        self.assertFalse(ProtocolSection.objects.exists())

    def test_a_section_holding_protocols_is_kept_with_the_reason(self):
        number = sections.add(self.competition, FINALS).number
        self._upload(section=number)
        self.client.force_login(self.author)
        with override("en"):
            response = self.client.post(
                f"/en/protocols/event/{self.competition.pk}/sections/",
                {"action": "delete", "number": number},
                follow=True,
            )
        self.assertContains(response, "still holds protocols")
        self.assertFalse(ProtocolSection.objects.get(number=number).is_deleted)

    def test_only_the_author_and_the_managers_reach_the_page(self):
        self.assertEqual(self.client.get(self._page()).status_code, HTTPStatus.FOUND)
        self.client.force_login(make_user("other", role=User.Role.ORGANIZER))
        self.assertEqual(self.client.get(self._page()).status_code, HTTPStatus.FORBIDDEN)
        self.client.force_login(make_user("admin", role=User.Role.ADMIN))
        self.assertEqual(self.client.get(self._page()).status_code, HTTPStatus.OK)

    def test_the_event_page_links_the_page_for_the_token_holder(self):
        self.client.force_login(self.author)
        page = self.client.get(f"/en/calendar/{self.competition.pk}/").content.decode()
        self.assertIn(f"/en/protocols/event/{self.competition.pk}/sections/", page)


class SectionsApiTest(_Event, TestCase):
    def _send(self, method, url, user, payload=None):
        send = getattr(self.client, method)
        if payload is None:
            return send(url, **_bearer(user))
        return send(url, json.dumps(payload), content_type="application/json", **_bearer(user))

    def test_the_organizer_lists_adds_renames_and_deletes_sections(self):
        added = self._send("post", _api(self.competition), self.author, {"name": FINALS})
        self.assertEqual(added.status_code, HTTPStatus.CREATED)
        self.assertEqual(added.json(), {"number": 2, "name": FINALS, "protocols": 0})
        renamed = self._send("patch", _api(self.competition, 2), self.author, {"name": {"en": "Final heats"}})
        self.assertEqual(renamed.json()["name"], {**FINALS, "en": "Final heats"})
        listed = self._send("get", _api(self.competition), self.author).json()
        self.assertEqual([row["number"] for row in listed], [1, 2])
        with override("kk"):
            self.assertEqual(listed[0]["name"]["kk"], gettext("Protocols"))
        self.assertEqual(
            self._send("delete", _api(self.competition, 2), self.author).status_code, HTTPStatus.NO_CONTENT
        )
        self.assertEqual(self._send("delete", _api(self.competition, 2), self.author).status_code, HTTPStatus.NOT_FOUND)

    def test_a_name_must_be_given_in_every_language(self):
        response = self._send("post", _api(self.competition), self.author, {"name": {"ru": "R", "en": "E"}})
        self.assertEqual(response.status_code, HTTPStatus.UNPROCESSABLE_ENTITY)
        self.assertIn("name.kk", response.json()["detail"])
        too_long = {**FINALS, "en": "x" * 201}
        response = self._send("post", _api(self.competition), self.author, {"name": too_long})
        self.assertEqual(response.status_code, HTTPStatus.UNPROCESSABLE_ENTITY)
        self.assertIn("name.en", response.json()["detail"])
        self.assertFalse(ProtocolSection.objects.exists())

    def test_a_section_with_protocols_or_the_first_is_not_deleted(self):
        number = sections.add(self.competition, FINALS).number
        self._upload(section=number)
        for target in (number, sections.FIRST):
            with self.subTest(section=target):
                response = self._send("delete", _api(self.competition, target), self.author)
                self.assertEqual(response.status_code, HTTPStatus.CONFLICT)
        self.assertIn(
            "still holds protocols", self._send("delete", _api(self.competition, number), self.author).json()["detail"]
        )

    def test_someone_elses_event_is_not_found(self):
        stranger = make_user("stranger", role=User.Role.ORGANIZER)
        self.assertEqual(self._send("get", _api(self.competition), stranger).status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(
            self._send("post", _api(self.competition), stranger, {"name": FINALS}).status_code, HTTPStatus.NOT_FOUND
        )
