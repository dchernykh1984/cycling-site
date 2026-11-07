"""Protocol sections (issue #452): an event's protocols under headings of their own, and the timing
software publishing into one by its number."""

from http import HTTPStatus

from django.test import Client, TestCase
from django.utils.translation import gettext, override

from accounts.models import User
from protocols import sections
from protocols.models import Protocol, ProtocolSection
from registrations.tests import make_competition, make_user
from tests.test_protocol_upload import _html, _MediaMixin, _stored_files

UPLOAD = "/api/v1/protocols/upload/"
DELETE = "/api/v1/protocols/delete/"
FINALS = {"ru": "Protokoly finalov", "kk": "Finaldyq hattamalar", "en": "Finals"}


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
