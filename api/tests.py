"""Tests for django-ninja API v1 endpoints."""

import shutil
import tempfile
import uuid
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import User
from calendar_app.models import Competition, Discipline, DisciplineCategory, EventType
from knowledge.models import DraftSubmission
from locations.models import Location
from registrations.models import CompetitionRegistration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(username, role=User.Role.PARTICIPANT, **kwargs):
    u = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="Pass1234!",
        role=role,
        **kwargs,
    )
    u.api_token = uuid.uuid4()
    u.save(update_fields=["api_token"])
    return u


def _competition(**kwargs):
    defaults = {
        "title_ru": "Race",
        "date_start": date(2026, 7, 1),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _location(**kwargs):
    defaults = {"name": "City", "name_ru": "City", "name_kk": "", "name_en": ""}
    defaults.update(kwargs)
    return Location.add_root(**defaults)


def _draft(author, submission_type=DraftSubmission.SubmissionType.NEWS, **kwargs):
    defaults = {
        "author": author,
        "submission_type": submission_type,
        "title": "My Draft",
        "body": "Body text",
        "locale": "ru",
        "category": "",
    }
    defaults.update(kwargs)
    return DraftSubmission.objects.create(**defaults)


def _registration(competition, **kwargs):
    defaults = {
        "competition": competition,
        "first_name": "Ivan",
        "last_name": "Petrov",
        "birth_date": date(1990, 6, 15),
        "gender": "M",
        "is_approved": True,
        "is_paid": True,
    }
    defaults.update(kwargs)
    return CompetitionRegistration.objects.create(**defaults)


class ApiTestMixin:
    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {user.api_token}"}

    def get(self, url, user=None, **kwargs):
        headers = self.auth(user) if user else {}
        return self.client.get(url, **headers, **kwargs)

    def post(self, url, data, user=None, content_type="application/json", **kwargs):
        headers = self.auth(user) if user else {}
        return self.client.post(url, data, content_type=content_type, **headers, **kwargs)

    def patch(self, url, data, user=None, content_type="application/json", **kwargs):
        headers = self.auth(user) if user else {}
        return self.client.patch(url, data, content_type=content_type, **headers, **kwargs)

    def delete(self, url, user=None, **kwargs):
        headers = self.auth(user) if user else {}
        return self.client.delete(url, **headers, **kwargs)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class IsAdminTest(TestCase):
    def test_admin_returns_true(self):
        from api.auth import is_admin

        user = _user("adm", role=User.Role.ADMIN)
        self.assertTrue(is_admin(user))

    def test_participant_returns_false(self):
        from api.auth import is_admin

        user = _user("par", role=User.Role.PARTICIPANT)
        self.assertFalse(is_admin(user))

    def test_superuser_returns_true(self):
        from api.auth import is_admin

        user = User.objects.create_superuser("sup", "s@s.com", "Pass1!")
        self.assertTrue(is_admin(user))


class ApiTokenAuthTest(TestCase, ApiTestMixin):
    def test_valid_token_authenticates(self):
        user = _user("org", role=User.Role.ORGANIZER)
        comp = _competition(submitted_by=user)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=user)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["competition_token"], str(comp.upload_token))

    def test_invalid_token_returns_401(self):
        resp = self.client.get(
            "/api/v1/competitions/",
            HTTP_AUTHORIZATION="Bearer not-a-real-token",
        )
        self.assertEqual(resp.status_code, 401)

    def test_no_token_returns_401(self):
        resp = self.client.get("/api/v1/competitions/")
        self.assertEqual(resp.status_code, 401)

    def test_no_token_on_locations_returns_401(self):
        resp = self.client.get("/api/v1/locations/")
        self.assertEqual(resp.status_code, 401)

    def test_participant_token_grants_read_access(self):
        participant = _user("par_read", role=User.Role.PARTICIPANT)
        resp = self.get("/api/v1/competitions/", user=participant)
        self.assertEqual(resp.status_code, 200)

    def test_participant_token_grants_location_read_access(self):
        participant = _user("par_loc", role=User.Role.PARTICIPANT)
        resp = self.get("/api/v1/locations/", user=participant)
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Competitions
# ---------------------------------------------------------------------------


class CompetitionListTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("reader", role=User.Role.PARTICIPANT)

    def test_returns_approved_by_default(self):
        _competition(status=Competition.Status.APPROVED)
        _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_non_admin_cannot_see_others_pending_via_status_filter(self):
        _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/?status=pending_approval", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)

    def test_non_admin_sees_own_pending_via_status_filter(self):
        _competition(status=Competition.Status.PENDING_APPROVAL, submitted_by=self.reader)
        _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/?status=pending_approval", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_admin_sees_all_pending_via_status_filter(self):
        admin = _user("list_admin", role=User.Role.ADMIN)
        _competition(status=Competition.Status.PENDING_APPROVAL)
        _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/?status=pending_approval", user=admin)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_filter_by_city_ids(self):
        city = _location()
        _competition(location=city)
        _competition()
        resp = self.get(f"/api/v1/competitions/?city_ids={city.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_filter_by_country_includes_child_locations(self):
        country = _location(name="Country", name_ru="Country")
        region = country.add_child(name="Region", name_ru="Region", name_kk="", name_en="")
        city = region.add_child(name="City", name_ru="City", name_kk="", name_en="")
        _competition(location=city)
        _competition()
        resp = self.get(f"/api/v1/competitions/?country_ids={country.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_filter_by_discipline_ids(self):
        cat = DisciplineCategory.objects.create(name="Road")
        disc = Discipline.objects.create(name="Race", category=cat)
        _competition(discipline=disc)
        _competition()
        resp = self.get(f"/api/v1/competitions/?discipline_ids={disc.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_filter_by_event_type_ids(self):
        et = EventType.objects.create(name="Stage race")
        _competition(event_type=et)
        _competition()
        resp = self.get(f"/api/v1/competitions/?event_type_ids={et.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_multiple_discipline_ids_or_logic(self):
        cat = DisciplineCategory.objects.create(name="Cat")
        d1 = Discipline.objects.create(name="D1", category=cat)
        d2 = Discipline.objects.create(name="D2", category=cat)
        _competition(discipline=d1)
        _competition(discipline=d2)
        _competition()
        resp = self.get(f"/api/v1/competitions/?discipline_ids={d1.pk}&discipline_ids={d2.pk}", user=self.reader)
        self.assertEqual(len(resp.json()), 2)

    def test_localized_title_in_response(self):
        _competition(title_ru="Race RU", title_kk="Race KK", title_en="Race")
        resp = self.get("/api/v1/competitions/", user=self.reader)
        data = resp.json()[0]
        self.assertEqual(data["title"]["ru"], "Race RU")
        self.assertEqual(data["title"]["kk"], "Race KK")
        self.assertEqual(data["title"]["en"], "Race")

    def test_anonymous_returns_401(self):
        resp = self.get("/api/v1/competitions/")
        self.assertEqual(resp.status_code, 401)


class CompetitionDetailTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("det_reader", role=User.Role.PARTICIPANT)

    def test_returns_competition(self):
        comp = _competition()
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], comp.pk)

    def test_token_shown_to_owner(self):
        owner = _user("owner", role=User.Role.ORGANIZER)
        comp = _competition(submitted_by=owner)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=owner)
        self.assertEqual(resp.json()["competition_token"], str(comp.upload_token))

    def test_token_hidden_from_stranger(self):
        stranger = _user("stranger", role=User.Role.PARTICIPANT)
        comp = _competition()
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=stranger)
        self.assertIsNone(resp.json()["competition_token"])

    def test_pending_competition_hidden_from_stranger(self):
        owner = _user("pending_owner", role=User.Role.ORGANIZER)
        comp = _competition(submitted_by=owner, status=Competition.Status.PENDING_APPROVAL)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 404)

    def test_owner_can_get_own_pending(self):
        owner = _user("own_pending", role=User.Role.ORGANIZER)
        comp = _competition(submitted_by=owner, status=Competition.Status.PENDING_APPROVAL)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=owner)
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_get_pending(self):
        admin = _user("det_admin", role=User.Role.ADMIN)
        comp = _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=admin)
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_returns_401(self):
        comp = _competition()
        resp = self.get(f"/api/v1/competitions/{comp.pk}")
        self.assertEqual(resp.status_code, 401)

    def test_404_for_missing(self):
        resp = self.get("/api/v1/competitions/99999", user=self.reader)
        self.assertEqual(resp.status_code, 404)


class CompetitionCreateTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.organizer = _user("org", role=User.Role.ORGANIZER)
        self.admin = _user("adm", role=User.Role.ADMIN)
        self.participant = _user("par", role=User.Role.PARTICIPANT)

    def _payload(self, **kwargs):
        defaults = {
            "title": {"ru": "Race RU", "kk": "", "en": ""},
            "description": {"ru": "", "kk": "", "en": ""},
            "date_start": "2026-07-01",
        }
        defaults.update(kwargs)
        return defaults

    def test_organizer_creates_pending(self):
        resp = self.post("/api/v1/competitions/", self._payload(), user=self.organizer)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], Competition.Status.PENDING_APPROVAL)

    def test_admin_creates_approved(self):
        resp = self.post("/api/v1/competitions/", self._payload(), user=self.admin)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], Competition.Status.APPROVED)

    def test_participant_forbidden(self):
        resp = self.post("/api/v1/competitions/", self._payload(), user=self.participant)
        self.assertEqual(resp.status_code, 403)

    def test_token_shown_to_creator(self):
        resp = self.post("/api/v1/competitions/", self._payload(), user=self.organizer)
        self.assertIsNotNone(resp.json()["competition_token"])

    def test_requires_auth(self):
        resp = self.post("/api/v1/competitions/", self._payload())
        self.assertEqual(resp.status_code, 401)


class CompetitionUpdateTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.owner = _user("owner", role=User.Role.ORGANIZER)
        self.admin = _user("adm", role=User.Role.ADMIN)
        self.stranger = _user("stranger", role=User.Role.ORGANIZER)
        self.comp = _competition(submitted_by=self.owner)

    def test_owner_can_update(self):
        resp = self.patch(
            f"/api/v1/competitions/{self.comp.pk}",
            {"title": {"ru": "New Title", "kk": "", "en": ""}},
            user=self.owner,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"]["ru"], "New Title")

    def test_stranger_forbidden(self):
        resp = self.patch(
            f"/api/v1/competitions/{self.comp.pk}",
            {"title": {"ru": "Hacked", "kk": "", "en": ""}},
            user=self.stranger,
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_update(self):
        resp = self.patch(
            f"/api/v1/competitions/{self.comp.pk}",
            {"title": {"ru": "Admin Title", "kk": "", "en": ""}},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_cannot_change_visibility(self):
        resp = self.patch(
            f"/api/v1/competitions/{self.comp.pk}",
            {"is_hidden": True},
            user=self.owner,
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_change_visibility(self):
        resp = self.patch(
            f"/api/v1/competitions/{self.comp.pk}",
            {"is_hidden": True},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_hidden"])


class CompetitionDeleteTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.owner = _user("owner", role=User.Role.ORGANIZER)
        self.stranger = _user("stranger", role=User.Role.ORGANIZER)
        self.comp = _competition(submitted_by=self.owner)

    def test_owner_can_delete(self):
        resp = self.delete(f"/api/v1/competitions/{self.comp.pk}", user=self.owner)
        self.assertEqual(resp.status_code, 204)
        self.comp.refresh_from_db()
        self.assertTrue(self.comp.is_deleted)

    def test_stranger_cannot_delete(self):
        resp = self.delete(f"/api/v1/competitions/{self.comp.pk}", user=self.stranger)
        self.assertEqual(resp.status_code, 403)

    def test_deleted_competition_not_in_list(self):
        self.delete(f"/api/v1/competitions/{self.comp.pk}", user=self.owner)
        resp = self.get("/api/v1/competitions/", user=self.owner)
        self.assertEqual(len(resp.json()), 0)


# ---------------------------------------------------------------------------
# Drafts (news)
# ---------------------------------------------------------------------------


class NewsDraftTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.author = _user("author", role=User.Role.PARTICIPANT)
        self.admin = _user("adm", role=User.Role.ADMIN)
        self.other = _user("other", role=User.Role.PARTICIPANT)

    def _payload(self, **kwargs):
        defaults = {"title": "Draft Title", "body": "Body", "locale": "ru", "category": ""}
        defaults.update(kwargs)
        return defaults

    def test_create_draft(self):
        resp = self.post("/api/v1/news/", self._payload(), user=self.author)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], DraftSubmission.Status.PENDING)

    def test_admin_create_auto_approves(self):
        resp = self.post("/api/v1/news/", self._payload(), user=self.admin)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], DraftSubmission.Status.APPROVED)

    def test_invalid_locale_rejected(self):
        resp = self.post("/api/v1/news/", self._payload(locale="xx"), user=self.author)
        self.assertEqual(resp.status_code, 422)

    def test_requires_participant_role(self):
        guest = _user("guest", role=User.Role.GUEST)
        resp = self.post("/api/v1/news/", self._payload(), user=guest)
        self.assertEqual(resp.status_code, 403)

    def test_author_sees_own_drafts(self):
        _draft(self.author)
        _draft(self.other)
        resp = self.get("/api/v1/news/", user=self.author)
        self.assertEqual(len(resp.json()), 1)

    def test_admin_sees_all_drafts(self):
        _draft(self.author)
        _draft(self.other)
        resp = self.get("/api/v1/news/", user=self.admin)
        self.assertEqual(len(resp.json()), 2)

    def test_get_draft_requires_owner_or_admin(self):
        draft = _draft(self.author)
        resp = self.get(f"/api/v1/news/{draft.pk}", user=self.other)
        self.assertEqual(resp.status_code, 403)

    def test_update_pending_draft(self):
        draft = _draft(self.author)
        resp = self.patch(f"/api/v1/news/{draft.pk}", {"title": "Updated"}, user=self.author)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Updated")

    def test_cannot_update_approved_draft(self):
        draft = _draft(self.admin)
        draft.status = DraftSubmission.Status.APPROVED
        draft.save(update_fields=["status"])
        resp = self.patch(f"/api/v1/news/{draft.pk}", {"title": "X"}, user=self.admin)
        self.assertEqual(resp.status_code, 409)

    def test_delete_pending_draft(self):
        draft = _draft(self.author)
        resp = self.delete(f"/api/v1/news/{draft.pk}", user=self.author)
        self.assertEqual(resp.status_code, 204)

    def test_cannot_delete_approved_draft(self):
        draft = _draft(self.admin)
        draft.status = DraftSubmission.Status.APPROVED
        draft.save(update_fields=["status"])
        resp = self.delete(f"/api/v1/news/{draft.pk}", user=self.admin)
        self.assertEqual(resp.status_code, 409)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


class LocationListTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("loc_reader", role=User.Role.PARTICIPANT)

    def test_hidden_location_excluded(self):
        before = len(self.get("/api/v1/locations/", user=self.reader).json())
        _location()
        _location(is_hidden=True)
        after = len(self.get("/api/v1/locations/", user=self.reader).json())
        self.assertEqual(after - before, 1)

    def test_include_hidden_param(self):
        before_all = len(self.get("/api/v1/locations/?include_hidden=true", user=self.reader).json())
        _location()
        hidden = _location(is_hidden=True)
        after_all = len(self.get("/api/v1/locations/?include_hidden=true", user=self.reader).json())
        self.assertEqual(after_all - before_all, 2)
        ids_visible = {d["id"] for d in self.get("/api/v1/locations/", user=self.reader).json()}
        self.assertNotIn(hidden.pk, ids_visible)

    def test_parent_id_computed_correctly(self):
        parent = _location(name="Parent", name_ru="Parent")
        child = parent.add_child(name="Child", name_ru="Child", name_kk="", name_en="")
        resp = self.get("/api/v1/locations/", user=self.reader)
        child_data = next(d for d in resp.json() if d["id"] == child.pk)
        self.assertEqual(child_data["parent_id"], parent.pk)

    def test_root_has_no_parent(self):
        loc = _location()
        resp = self.get("/api/v1/locations/", user=self.reader)
        loc_data = next(d for d in resp.json() if d["id"] == loc.pk)
        self.assertIsNone(loc_data["parent_id"])

    def test_anonymous_returns_401(self):
        resp = self.get("/api/v1/locations/")
        self.assertEqual(resp.status_code, 401)


class LocationDetailTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("loc_det_reader", role=User.Role.PARTICIPANT)

    def test_get_location(self):
        loc = _location()
        resp = self.get(f"/api/v1/locations/{loc.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], loc.pk)

    def test_404_for_missing(self):
        resp = self.get("/api/v1/locations/99999", user=self.reader)
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_returns_401(self):
        loc = _location()
        resp = self.get(f"/api/v1/locations/{loc.pk}")
        self.assertEqual(resp.status_code, 401)


class LocationCreateTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.admin = _user("adm", role=User.Role.ADMIN)
        self.organizer = _user("org", role=User.Role.ORGANIZER)

    def test_admin_can_create(self):
        resp = self.post(
            "/api/v1/locations/",
            {"name": {"ru": "Almaty RU", "kk": "Almaty RU", "en": "Almaty"}},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"]["ru"], "Almaty RU")

    def test_organizer_forbidden(self):
        resp = self.post(
            "/api/v1/locations/",
            {"name": {"ru": "City RU", "kk": "", "en": ""}},
            user=self.organizer,
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_with_parent(self):
        parent = _location()
        resp = self.post(
            "/api/v1/locations/",
            {"name": {"ru": "Child RU", "kk": "", "en": ""}, "parent_id": parent.pk},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["parent_id"], parent.pk)

    def test_invalid_parent_404(self):
        resp = self.post(
            "/api/v1/locations/",
            {"name": {"ru": "X", "kk": "", "en": ""}, "parent_id": 99999},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 404)


class LocationUpdateTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.admin = _user("adm", role=User.Role.ADMIN)
        self.loc = _location()

    def test_admin_can_update(self):
        resp = self.patch(
            f"/api/v1/locations/{self.loc.pk}",
            {"name": {"ru": "New RU", "kk": "", "en": ""}},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"]["ru"], "New RU")


class LocationDeleteTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.admin = _user("adm", role=User.Role.ADMIN)
        self.loc = _location()

    def test_admin_soft_deletes(self):
        resp = self.delete(f"/api/v1/locations/{self.loc.pk}", user=self.admin)
        self.assertEqual(resp.status_code, 204)
        self.loc.refresh_from_db()
        self.assertTrue(self.loc.is_deleted)

    def test_deleted_not_in_list(self):
        before = len(self.get("/api/v1/locations/", user=self.admin).json())
        self.delete(f"/api/v1/locations/{self.loc.pk}", user=self.admin)
        after = len(self.get("/api/v1/locations/", user=self.admin).json())
        self.assertEqual(after, before - 1)


# ---------------------------------------------------------------------------
# Protocol upload (extra coverage for uncovered lines)
# ---------------------------------------------------------------------------


def _html_file(content: bytes = b"<html></html>", name: str = "p.html") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="text/html")


class ProtocolExtraCoverageTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self._settings = override_settings(MEDIA_ROOT=self.media_root)
        self._settings.enable()
        self.comp = Competition.objects.create(
            title_ru="Race",
            date_start=date(2026, 7, 1),
            status=Competition.Status.APPROVED,
        )

    def tearDown(self):
        self._settings.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _post(self, **kwargs):
        data = {
            "competition_token": str(self.comp.upload_token),
            "protocol_type": "absolute",
            "html_file": _html_file(),
        }
        data.update(kwargs)
        return self.client.post("/api/v1/protocols/upload/", data)

    def test_non_html_content_rejected(self):
        resp = self._post(html_file=_html_file(b"not html content at all!", "p.html"))
        self.assertEqual(resp.status_code, 400)

    def test_htm_extension_accepted(self):
        resp = self._post(html_file=_html_file(b"<html></html>", "p.htm"))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Knowledge article drafts
# ---------------------------------------------------------------------------


class KnowledgeArticleDraftTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.author = _user("k_author", role=User.Role.PARTICIPANT)
        self.other = _user("k_other", role=User.Role.PARTICIPANT)

    def _payload(self, **kwargs):
        defaults = {"title": "Article Title", "body": "Body", "locale": "ru", "category": ""}
        defaults.update(kwargs)
        return defaults

    def test_create_knowledge_draft(self):
        resp = self.post("/api/v1/knowledge/", self._payload(), user=self.author)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["submission_type"], DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)

    def test_knowledge_draft_not_visible_via_news_endpoint(self):
        kdraft = _draft(self.author, submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        resp = self.get("/api/v1/news/", user=self.author)
        ids = [d["id"] for d in resp.json()]
        self.assertNotIn(kdraft.pk, ids)

    def test_news_draft_not_visible_via_knowledge_endpoint(self):
        ndraft = _draft(self.author, submission_type=DraftSubmission.SubmissionType.NEWS)
        resp = self.get("/api/v1/knowledge/", user=self.author)
        ids = [d["id"] for d in resp.json()]
        self.assertNotIn(ndraft.pk, ids)

    def test_other_user_cannot_access_knowledge_draft(self):
        kdraft = _draft(self.author, submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        resp = self.get(f"/api/v1/knowledge/{kdraft.pk}", user=self.other)
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------


class ParticipantsAPITest(TestCase, ApiTestMixin):
    def setUp(self):
        self.comp = _competition()

    def test_returns_participants(self):
        _registration(self.comp)
        resp = self.get(f"/api/v1/participants/?competition_token={self.comp.upload_token}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["competition_id"], self.comp.pk)
        self.assertEqual(len(data["participants"]), 1)

    def test_invalid_token_returns_401(self):
        resp = self.get("/api/v1/participants/?competition_token=not-a-valid-uuid")
        self.assertEqual(resp.status_code, 401)

    def test_unknown_token_returns_401(self):
        resp = self.get(f"/api/v1/participants/?competition_token={uuid.uuid4()}")
        self.assertEqual(resp.status_code, 401)

    def test_deleted_competition_returns_401(self):
        self.comp.is_deleted = True
        self.comp.save(update_fields=["is_deleted"])
        resp = self.get(f"/api/v1/participants/?competition_token={self.comp.upload_token}")
        self.assertEqual(resp.status_code, 401)

    def test_pending_competition_returns_401(self):
        comp = _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get(f"/api/v1/participants/?competition_token={comp.upload_token}")
        self.assertEqual(resp.status_code, 401)

    def test_unapproved_excluded_when_approval_required(self):
        self.comp.require_approval = True
        self.comp.save(update_fields=["require_approval"])
        _registration(self.comp, is_approved=True)
        _registration(self.comp, is_approved=False, first_name="Unapproved")
        resp = self.get(f"/api/v1/participants/?competition_token={self.comp.upload_token}")
        self.assertEqual(len(resp.json()["participants"]), 1)

    def test_all_returned_when_no_approval_required(self):
        _registration(self.comp, is_approved=False)
        _registration(self.comp, is_approved=True)
        resp = self.get(f"/api/v1/participants/?competition_token={self.comp.upload_token}")
        self.assertEqual(len(resp.json()["participants"]), 2)


# ---------------------------------------------------------------------------
# Protocol upload (success paths)
# ---------------------------------------------------------------------------


class ProtocolUploadSuccessTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self._settings = override_settings(MEDIA_ROOT=self.media_root)
        self._settings.enable()
        self.comp = Competition.objects.create(
            title_ru="Race",
            date_start=date(2026, 7, 1),
            status=Competition.Status.APPROVED,
        )

    def tearDown(self):
        self._settings.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _post(self, **kwargs):
        data = {
            "competition_token": str(self.comp.upload_token),
            "protocol_type": "absolute",
            "html_file": SimpleUploadedFile("p.html", b"<html></html>", content_type="text/html"),
        }
        data.update(kwargs)
        return self.client.post("/api/v1/protocols/upload/", data)

    def test_success_returns_id_and_hash(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        self.assertIn("file_hash", data)

    def test_invalid_token_returns_401(self):
        resp = self._post(competition_token=str(uuid.uuid4()))
        self.assertEqual(resp.status_code, 401)

    def test_deleted_competition_returns_401(self):
        self.comp.is_deleted = True
        self.comp.save(update_fields=["is_deleted"])
        resp = self._post()
        self.assertEqual(resp.status_code, 401)

    def test_invalid_protocol_type_returns_400(self):
        resp = self._post(protocol_type="invalid")
        self.assertEqual(resp.status_code, 400)

    def test_group_protocol_type_accepted(self):
        resp = self._post(protocol_type="group")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Disciplines & EventTypes
# ---------------------------------------------------------------------------


class DisciplineListTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("disc_reader", role=User.Role.PARTICIPANT)
        self.cat = DisciplineCategory.objects.create(name="Road", name_ru="Road_ru", name_kk="", name_en="Road")
        self.disc = Discipline.objects.create(
            name="Race", name_ru="Race_ru", name_kk="", name_en="Race", category=self.cat
        )

    def test_returns_categories_with_disciplines(self):
        resp = self.get("/api/v1/disciplines/", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        cat_data = next((d for d in data if d["id"] == self.cat.pk), None)
        self.assertIsNotNone(cat_data)
        self.assertEqual(cat_data["name"]["ru"], "Road_ru")
        disc_ids = [d["id"] for d in cat_data["disciplines"]]
        self.assertIn(self.disc.pk, disc_ids)
        disc_data = next(d for d in cat_data["disciplines"] if d["id"] == self.disc.pk)
        self.assertEqual(disc_data["name"]["en"], "Race")

    def test_get_single_category(self):
        resp = self.get(f"/api/v1/disciplines/{self.cat.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], self.cat.pk)

    def test_404_for_missing_category(self):
        resp = self.get("/api/v1/disciplines/99999", user=self.reader)
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_returns_401(self):
        resp = self.get("/api/v1/disciplines/")
        self.assertEqual(resp.status_code, 401)


class EventTypeListTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("et_reader", role=User.Role.PARTICIPANT)
        self.et = EventType.objects.create(name="Stage race", name_ru="Stage_ru", name_kk="", name_en="Stage race")

    def test_returns_event_types(self):
        resp = self.get("/api/v1/event-types/", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [d["id"] for d in data]
        self.assertIn(self.et.pk, ids)
        entry = next(d for d in data if d["id"] == self.et.pk)
        self.assertEqual(entry["name"]["ru"], "Stage_ru")
        self.assertEqual(entry["name"]["en"], "Stage race")

    def test_anonymous_returns_401(self):
        resp = self.get("/api/v1/event-types/")
        self.assertEqual(resp.status_code, 401)
