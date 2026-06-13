"""Tests for django-ninja API v1 endpoints."""

import shutil
import tempfile
import uuid
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings

from accounts.models import User
from calendar_app.models import Competition, Discipline, DisciplineCategory, EventType
from knowledge.models import DraftSubmission
from locations.models import Location
from news.models import NewsArticle
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


def _article(**kwargs):
    defaults = {
        "title_ru": "Title RU",
        "title_kk": "Title KK",
        "title_en": "Title EN",
        "intro_ru": "Intro RU",
        "intro_kk": "Intro KK",
        "intro_en": "Intro EN",
        "body_ru": "Body RU",
        "body_kk": "Body KK",
        "body_en": "Body EN",
    }
    defaults.update(kwargs)
    return NewsArticle.objects.create(**defaults)


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

    def test_anonymous_user_returns_false(self):
        from django.contrib.auth.models import AnonymousUser

        from api.auth import is_admin

        self.assertFalse(is_admin(AnonymousUser()))


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

    def test_no_token_returns_200_on_public_list(self):
        resp = self.client.get("/api/v1/competitions/")
        self.assertEqual(resp.status_code, 200)

    def test_no_token_on_locations_returns_200(self):
        resp = self.client.get("/api/v1/locations/")
        self.assertEqual(resp.status_code, 200)

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

    def test_filter_by_location_ids(self):
        city = _location()
        _competition(location=city)
        _competition()
        resp = self.get(f"/api/v1/competitions/?location_ids={city.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_filter_by_location_includes_descendants(self):
        country = _location(name="Country", name_ru="Country")
        region = country.add_child(name="Region", name_ru="Region", name_kk="", name_en="")
        city = region.add_child(name="City", name_ru="City", name_kk="", name_en="")
        _competition(location=city)
        _competition()
        resp = self.get(f"/api/v1/competitions/?location_ids={country.pk}", user=self.reader)
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

    def test_hidden_competition_not_in_list_for_non_admin(self):
        _competition(is_hidden=True)
        resp = self.get("/api/v1/competitions/", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)

    def test_hidden_competition_visible_to_owner(self):
        owner = _user("hidden_owner", role=User.Role.ORGANIZER)
        _competition(submitted_by=owner, is_hidden=True)
        resp = self.get("/api/v1/competitions/", user=owner)
        self.assertEqual(len(resp.json()), 1)

    def test_hidden_competition_visible_to_admin(self):
        admin = _user("hidden_admin", role=User.Role.ADMIN)
        _competition(is_hidden=True)
        resp = self.get("/api/v1/competitions/", user=admin)
        self.assertEqual(len(resp.json()), 1)

    def test_filter_by_multiple_location_ids_uses_or_semantics(self):
        loc_a = _location(name="LocA", name_ru="LocA")
        loc_b = _location(name="LocB", name_ru="LocB")
        _competition(location=loc_a)
        _competition(location=loc_b)
        _competition()
        resp = self.get(
            f"/api/v1/competitions/?location_ids={loc_a.pk}&location_ids={loc_b.pk}",
            user=self.reader,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_localized_title_in_response(self):
        _competition(title_ru="Race RU", title_kk="Race KK", title_en="Race")
        resp = self.get("/api/v1/competitions/", user=self.reader)
        data = resp.json()[0]
        self.assertEqual(data["title"]["ru"], "Race RU")
        self.assertEqual(data["title"]["kk"], "Race KK")
        self.assertEqual(data["title"]["en"], "Race")

    def test_anonymous_sees_only_approved_visible(self):
        _competition(status=Competition.Status.APPROVED, is_hidden=False)
        _competition(status=Competition.Status.APPROVED, is_hidden=True)
        _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)


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

    def test_hidden_competition_returns_404_for_stranger(self):
        comp = _competition(is_hidden=True)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=self.reader)
        self.assertEqual(resp.status_code, 404)

    def test_hidden_competition_accessible_to_owner(self):
        owner = _user("hidden_det_owner", role=User.Role.ORGANIZER)
        comp = _competition(submitted_by=owner, is_hidden=True)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=owner)
        self.assertEqual(resp.status_code, 200)

    def test_hidden_competition_accessible_to_admin(self):
        admin = _user("hidden_det_admin", role=User.Role.ADMIN)
        comp = _competition(is_hidden=True)
        resp = self.get(f"/api/v1/competitions/{comp.pk}", user=admin)
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_can_get_approved_competition(self):
        comp = _competition()
        resp = self.get(f"/api/v1/competitions/{comp.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["competition_token"])

    def test_anonymous_hidden_competition_returns_404(self):
        comp = _competition(is_hidden=True)
        resp = self.get(f"/api/v1/competitions/{comp.pk}")
        self.assertEqual(resp.status_code, 404)

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

    def test_stranger_gets_404_for_pending_competition(self):
        pending = _competition(submitted_by=self.owner, status=Competition.Status.PENDING_APPROVAL)
        resp = self.patch(
            f"/api/v1/competitions/{pending.pk}",
            {"title": {"ru": "X", "kk": "", "en": ""}},
            user=self.stranger,
        )
        self.assertEqual(resp.status_code, 404)

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

    def test_stranger_gets_404_for_pending_competition(self):
        pending = _competition(submitted_by=self.owner, status=Competition.Status.PENDING_APPROVAL)
        resp = self.delete(f"/api/v1/competitions/{pending.pk}", user=self.stranger)
        self.assertEqual(resp.status_code, 404)

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

    def test_published_article_visible_to_authenticated_users(self):
        article = _article()
        resp = self.get("/api/v1/news/", user=self.author)
        self.assertIn(article.pk, [d["id"] for d in resp.json()])

    def test_any_user_can_get_published_article(self):
        article = _article()
        resp = self.get(f"/api/v1/news/{article.pk}", user=self.other)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], article.pk)

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

    def test_anonymous_can_list_published_articles(self):
        article = _article()
        resp = self.get("/api/v1/news/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(article.pk, [d["id"] for d in resp.json()])

    def test_hidden_article_not_in_public_list(self):
        _article(is_hidden=True)
        resp = self.get("/api/v1/news/")
        self.assertEqual(resp.json(), [])

    def test_admin_sees_hidden_article_in_list(self):
        article = _article(is_hidden=True)
        resp = self.get("/api/v1/news/", user=self.admin)
        self.assertIn(article.pk, [d["id"] for d in resp.json()])

    def test_anonymous_can_get_published_article(self):
        article = _article()
        resp = self.get(f"/api/v1/news/{article.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], article.pk)

    def test_hidden_article_returns_404_for_anonymous(self):
        article = _article(is_hidden=True)
        resp = self.get(f"/api/v1/news/{article.pk}")
        self.assertEqual(resp.status_code, 404)

    def test_news_submission_draft_not_in_article_list(self):
        _draft(self.author)
        resp = self.get("/api/v1/news/")
        self.assertEqual(resp.json(), [])

    def test_article_returns_all_locale_fields(self):
        article = _article(
            title_ru="Title RU",
            title_kk="Title KK",
            title_en="Title EN",
            intro_ru="Intro RU",
            intro_kk="Intro KK",
            intro_en="Intro EN",
            body_ru="Body RU",
            body_kk="Body KK",
            body_en="Body EN",
        )
        resp = self.get(f"/api/v1/news/{article.pk}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"]["ru"], "Title RU")
        self.assertEqual(data["title"]["kk"], "Title KK")
        self.assertEqual(data["title"]["en"], "Title EN")
        self.assertEqual(data["intro"]["ru"], "Intro RU")
        self.assertEqual(data["intro"]["kk"], "Intro KK")
        self.assertEqual(data["intro"]["en"], "Intro EN")
        self.assertEqual(data["body"]["ru"], "Body RU")
        self.assertEqual(data["body"]["kk"], "Body KK")
        self.assertEqual(data["body"]["en"], "Body EN")

    def test_article_locale_fields_in_list_response(self):
        _article(title_ru="RU Title", title_kk="KK Title", title_en="EN Title")
        resp = self.get("/api/v1/news/")
        data = resp.json()[0]
        self.assertEqual(data["title"]["ru"], "RU Title")
        self.assertEqual(data["title"]["kk"], "KK Title")
        self.assertEqual(data["title"]["en"], "EN Title")

    def test_invalid_token_still_returns_401_on_public_endpoints(self):
        resp = self.client.get("/api/v1/competitions/", HTTP_AUTHORIZATION="Bearer bad-token")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


class LocationListTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("loc_reader", role=User.Role.PARTICIPANT)
        self.admin = _user("loc_list_adm", role=User.Role.ADMIN)

    def _api_location(self, name_ru="City", name_kk="", name_en="", parent_id=None, is_hidden=False):
        payload = {"name": {"ru": name_ru, "kk": name_kk, "en": name_en}, "is_hidden": is_hidden}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        resp = self.post("/api/v1/locations/", payload, user=self.admin)
        self.assertEqual(resp.status_code, 201)
        return resp.json()

    def test_hidden_location_excluded(self):
        before = len(self.get("/api/v1/locations/", user=self.reader).json())
        self._api_location()
        self._api_location(is_hidden=True)
        after = len(self.get("/api/v1/locations/", user=self.reader).json())
        self.assertEqual(after - before, 1)

    def test_include_hidden_param(self):
        before_all = len(self.get("/api/v1/locations/?include_hidden=true", user=self.reader).json())
        self._api_location()
        hidden = self._api_location(is_hidden=True)
        after_all = len(self.get("/api/v1/locations/?include_hidden=true", user=self.reader).json())
        self.assertEqual(after_all - before_all, 2)
        ids_visible = {d["id"] for d in self.get("/api/v1/locations/", user=self.reader).json()}
        self.assertNotIn(hidden["id"], ids_visible)

    def test_tree_nests_children_under_parent(self):
        parent = self._api_location(name_ru="Parent")
        child = self._api_location(name_ru="Child", parent_id=parent["id"])
        resp = self.get("/api/v1/locations/", user=self.reader)
        data = resp.json()
        parent_data = next(d for d in data if d["id"] == parent["id"])
        child_ids = [c["id"] for c in parent_data["children"]]
        self.assertIn(child["id"], child_ids)

    def test_root_nodes_appear_at_top_level(self):
        loc = self._api_location()
        resp = self.get("/api/v1/locations/", user=self.reader)
        top_ids = [d["id"] for d in resp.json()]
        self.assertIn(loc["id"], top_ids)

    def test_deep_tree_nests_correctly(self):
        country = self._api_location(name_ru="Country")
        region = self._api_location(name_ru="Region", parent_id=country["id"])
        city = self._api_location(name_ru="City", parent_id=region["id"])
        resp = self.get("/api/v1/locations/", user=self.reader)
        data = resp.json()
        country_data = next(d for d in data if d["id"] == country["id"])
        region_data = next(d for d in country_data["children"] if d["id"] == region["id"])
        city_ids = [c["id"] for c in region_data["children"]]
        self.assertIn(city["id"], city_ids)

    def test_name_falls_back_to_canonical_when_locale_variants_empty(self):
        # Simulate pre-modeltranslation data: only the canonical `name` column has a value.
        loc = self._api_location()
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE locations_location SET name=%s, name_ru=%s, name_kk=%s, name_en=%s WHERE id=%s",
                ["FallbackCity", "", "", "", loc["id"]],
            )
        resp = self.get("/api/v1/locations/", user=self.reader)
        data = resp.json()
        node = next(d for d in data if d["id"] == loc["id"])
        self.assertEqual(node["name"]["ru"], "FallbackCity")
        self.assertEqual(node["name"]["kk"], "FallbackCity")
        self.assertEqual(node["name"]["en"], "FallbackCity")

    def test_name_falls_back_to_canonical_when_locale_variants_null(self):
        # Pre-migration rows may have NULL (not empty string) in locale columns.
        loc = self._api_location()
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE locations_location SET name=%s, name_ru=NULL, name_kk=NULL, name_en=NULL WHERE id=%s",
                ["NullFallback", loc["id"]],
            )
        resp = self.get("/api/v1/locations/", user=self.reader)
        data = resp.json()
        node = next(d for d in data if d["id"] == loc["id"])
        self.assertEqual(node["name"]["ru"], "NullFallback")
        self.assertEqual(node["name"]["kk"], "NullFallback")
        self.assertEqual(node["name"]["en"], "NullFallback")

    def test_locale_variant_takes_precedence_over_canonical(self):
        loc = self._api_location()
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE locations_location SET name=%s, name_ru=%s, name_kk=%s, name_en=%s WHERE id=%s",
                ["Canonical", "RuName", "", "", loc["id"]],
            )
        resp = self.get("/api/v1/locations/", user=self.reader)
        data = resp.json()
        node = next(d for d in data if d["id"] == loc["id"])
        self.assertEqual(node["name"]["ru"], "RuName")
        self.assertEqual(node["name"]["kk"], "Canonical")
        self.assertEqual(node["name"]["en"], "Canonical")

    def test_anonymous_can_list_locations(self):
        resp = self.get("/api/v1/locations/")
        self.assertEqual(resp.status_code, 200)

    def test_localized_name_in_list_response(self):
        loc = self._api_location(name_ru="City RU", name_kk="City KK", name_en="City EN")
        resp = self.get("/api/v1/locations/", user=self.reader)
        data = next(d for d in resp.json() if d["id"] == loc["id"])
        self.assertEqual(data["name"]["ru"], "City RU")
        self.assertEqual(data["name"]["kk"], "City KK")
        self.assertEqual(data["name"]["en"], "City EN")


class LocationDetailTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.reader = _user("loc_det_reader", role=User.Role.PARTICIPANT)
        self.admin = _user("loc_det_adm", role=User.Role.ADMIN)

    def _api_location(self, name_ru="City", name_kk="", name_en="", parent_id=None, is_hidden=False):
        payload = {"name": {"ru": name_ru, "kk": name_kk, "en": name_en}, "is_hidden": is_hidden}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        resp = self.post("/api/v1/locations/", payload, user=self.admin)
        self.assertEqual(resp.status_code, 201)
        return resp.json()

    def test_get_location(self):
        loc = self._api_location()
        resp = self.get(f"/api/v1/locations/{loc['id']}", user=self.reader)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], loc["id"])

    def test_404_for_missing(self):
        resp = self.get("/api/v1/locations/99999", user=self.reader)
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_can_get_location(self):
        loc = self._api_location()
        resp = self.get(f"/api/v1/locations/{loc['id']}")
        self.assertEqual(resp.status_code, 200)

    def test_localized_name_in_detail_response(self):
        loc = self._api_location(name_ru="City RU", name_kk="City KK", name_en="City EN")
        resp = self.get(f"/api/v1/locations/{loc['id']}", user=self.reader)
        data = resp.json()
        self.assertEqual(data["name"]["ru"], "City RU")
        self.assertEqual(data["name"]["kk"], "City KK")
        self.assertEqual(data["name"]["en"], "City EN")


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
        _draft(self.author, submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        article = _article()
        resp = self.get("/api/v1/news/", user=self.author)
        ids = [d["id"] for d in resp.json()]
        self.assertEqual(ids, [article.pk])

    def test_news_draft_not_visible_via_knowledge_endpoint(self):
        ndraft = _draft(self.author, submission_type=DraftSubmission.SubmissionType.NEWS)
        resp = self.get("/api/v1/knowledge/?status=pending", user=self.author)
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

    def test_anonymous_can_list_disciplines(self):
        resp = self.get("/api/v1/disciplines/")
        self.assertEqual(resp.status_code, 200)


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

    def test_anonymous_can_list_event_types(self):
        resp = self.get("/api/v1/event-types/")
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# Competition - full locale CRUD + web view verification
# ===========================================================================


class CompetitionLocaleCRUDTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.admin = _user("cl_admin", role=User.Role.ADMIN)
        self.reader = _user("cl_reader", role=User.Role.PARTICIPANT)

    def _create(self, **overrides):
        payload = {
            "title": {"ru": "Title RU", "kk": "Title KK", "en": "Title EN"},
            "description": {"ru": "Desc RU", "kk": "Desc KK", "en": "Desc EN"},
            "date_start": "2026-07-01",
        }
        payload.update(overrides)
        resp = self.post("/api/v1/competitions/", payload, user=self.admin)
        self.assertEqual(resp.status_code, 201)
        return resp.json()["id"]

    def test_detail_returns_all_locale_title_fields(self):
        pk = self._create()
        data = self.get(f"/api/v1/competitions/{pk}", user=self.reader).json()
        self.assertEqual(data["title"]["ru"], "Title RU")
        self.assertEqual(data["title"]["kk"], "Title KK")
        self.assertEqual(data["title"]["en"], "Title EN")

    def test_detail_returns_all_locale_description_fields(self):
        pk = self._create()
        data = self.get(f"/api/v1/competitions/{pk}", user=self.reader).json()
        self.assertEqual(data["description"]["ru"], "Desc RU")
        self.assertEqual(data["description"]["kk"], "Desc KK")
        self.assertEqual(data["description"]["en"], "Desc EN")

    def test_list_returns_all_locale_fields(self):
        pk = self._create()
        entries = self.get("/api/v1/competitions/", user=self.reader).json()
        entry = next(e for e in entries if e["id"] == pk)
        self.assertEqual(entry["title"]["ru"], "Title RU")
        self.assertEqual(entry["title"]["kk"], "Title KK")
        self.assertEqual(entry["title"]["en"], "Title EN")
        self.assertEqual(entry["description"]["ru"], "Desc RU")

    def test_patch_updates_all_locale_title_fields(self):
        pk = self._create()
        self.patch(
            f"/api/v1/competitions/{pk}",
            {"title": {"ru": "New RU", "kk": "New KK", "en": "New EN"}},
            user=self.admin,
        )
        data = self.get(f"/api/v1/competitions/{pk}", user=self.admin).json()
        self.assertEqual(data["title"]["ru"], "New RU")
        self.assertEqual(data["title"]["kk"], "New KK")
        self.assertEqual(data["title"]["en"], "New EN")

    def test_delete_removes_competition_from_api(self):
        pk = self._create()
        self.delete(f"/api/v1/competitions/{pk}", user=self.admin)
        self.assertEqual(self.get(f"/api/v1/competitions/{pk}", user=self.admin).status_code, 404)

    def test_competition_visible_in_web_view_after_api_create(self):
        pk = self._create()
        resp = self.client.get(f"/calendar/{pk}/")
        self.assertEqual(resp.status_code, 200)

    def test_web_form_creates_competition_with_all_locale_fields_visible_via_api(self):
        organizer = _user("wf_org", role=User.Role.ORGANIZER)
        self.client.force_login(organizer)
        self.client.post(
            "/calendar/submit/",
            {
                "title_ru": "Form RU",
                "title_kk": "Form KK",
                "title_en": "Form EN",
                "date_start": "2026-07-01",
            },
        )
        resp = self.get("/api/v1/competitions/", user=organizer)
        entry = next((c for c in resp.json() if c["title"]["ru"] == "Form RU"), None)
        self.assertIsNotNone(entry, "Competition created via web form not visible in API")
        self.assertEqual(entry["title"]["kk"], "Form KK")
        self.assertEqual(entry["title"]["en"], "Form EN")


# ===========================================================================
# Competition - access control: every role x every endpoint
# ===========================================================================


class CompetitionAccessTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.guest = _user("ca_guest", role=User.Role.GUEST)
        self.participant = _user("ca_par", role=User.Role.PARTICIPANT)
        self.organizer = _user("ca_org", role=User.Role.ORGANIZER)
        self.owner = _user("ca_owner", role=User.Role.ORGANIZER)
        self.admin = _user("ca_admin", role=User.Role.ADMIN)
        self.approved = _competition()
        self.hidden = _competition(is_hidden=True)
        self.owned = _competition(submitted_by=self.owner)

    def _payload(self):
        return {
            "title": {"ru": "T", "kk": "", "en": ""},
            "description": {"ru": "", "kk": "", "en": ""},
            "date_start": "2026-07-01",
        }

    # --- GET list ---

    def test_list_anonymous_sees_approved_visible(self):
        resp = self.get("/api/v1/competitions/")
        self.assertEqual(resp.status_code, 200)
        ids = [c["id"] for c in resp.json()]
        self.assertIn(self.approved.pk, ids)
        self.assertNotIn(self.hidden.pk, ids)

    def test_list_participant_does_not_see_hidden(self):
        ids = [c["id"] for c in self.get("/api/v1/competitions/", user=self.participant).json()]
        self.assertNotIn(self.hidden.pk, ids)

    def test_list_admin_sees_hidden(self):
        ids = [c["id"] for c in self.get("/api/v1/competitions/", user=self.admin).json()]
        self.assertIn(self.hidden.pk, ids)

    def test_list_owner_sees_own_hidden(self):
        hidden_owned = _competition(submitted_by=self.owner, is_hidden=True)
        ids = [c["id"] for c in self.get("/api/v1/competitions/", user=self.owner).json()]
        self.assertIn(hidden_owned.pk, ids)

    def test_list_participant_cannot_see_others_pending(self):
        pending = _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/?status=pending_approval", user=self.participant)
        ids = [c["id"] for c in resp.json()]
        self.assertNotIn(pending.pk, ids)

    def test_list_owner_sees_own_pending(self):
        pending = _competition(submitted_by=self.owner, status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/?status=pending_approval", user=self.owner)
        ids = [c["id"] for c in resp.json()]
        self.assertIn(pending.pk, ids)

    def test_list_admin_sees_all_pending(self):
        pending = _competition(status=Competition.Status.PENDING_APPROVAL)
        resp = self.get("/api/v1/competitions/?status=pending_approval", user=self.admin)
        ids = [c["id"] for c in resp.json()]
        self.assertIn(pending.pk, ids)

    # --- GET detail ---

    def test_detail_anonymous_gets_approved_visible(self):
        self.assertEqual(self.get(f"/api/v1/competitions/{self.approved.pk}").status_code, 200)

    def test_detail_anonymous_404_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/competitions/{self.hidden.pk}").status_code, 404)

    def test_detail_guest_404_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/competitions/{self.hidden.pk}", user=self.guest).status_code, 404)

    def test_detail_participant_404_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/competitions/{self.hidden.pk}", user=self.participant).status_code, 404)

    def test_detail_admin_200_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/competitions/{self.hidden.pk}", user=self.admin).status_code, 200)

    def test_detail_owner_200_for_own_hidden(self):
        hidden_owned = _competition(submitted_by=self.owner, is_hidden=True)
        self.assertEqual(self.get(f"/api/v1/competitions/{hidden_owned.pk}", user=self.owner).status_code, 200)

    def test_detail_non_owner_404_for_pending(self):
        pending = _competition(status=Competition.Status.PENDING_APPROVAL)
        self.assertEqual(self.get(f"/api/v1/competitions/{pending.pk}", user=self.participant).status_code, 404)

    def test_detail_owner_200_for_own_pending(self):
        pending = _competition(submitted_by=self.owner, status=Competition.Status.PENDING_APPROVAL)
        self.assertEqual(self.get(f"/api/v1/competitions/{pending.pk}", user=self.owner).status_code, 200)

    def test_detail_admin_200_for_pending(self):
        pending = _competition(status=Competition.Status.PENDING_APPROVAL)
        self.assertEqual(self.get(f"/api/v1/competitions/{pending.pk}", user=self.admin).status_code, 200)

    def test_detail_token_hidden_from_non_owner(self):
        data = self.get(f"/api/v1/competitions/{self.approved.pk}", user=self.participant).json()
        self.assertIsNone(data["competition_token"])

    def test_detail_token_visible_to_owner(self):
        data = self.get(f"/api/v1/competitions/{self.owned.pk}", user=self.owner).json()
        self.assertIsNotNone(data["competition_token"])

    def test_detail_token_visible_to_admin(self):
        data = self.get(f"/api/v1/competitions/{self.approved.pk}", user=self.admin).json()
        self.assertIsNotNone(data["competition_token"])

    # --- POST create ---

    def test_create_anonymous_returns_401(self):
        self.assertEqual(self.post("/api/v1/competitions/", self._payload()).status_code, 401)

    def test_create_guest_returns_403(self):
        self.assertEqual(self.post("/api/v1/competitions/", self._payload(), user=self.guest).status_code, 403)

    def test_create_participant_returns_403(self):
        self.assertEqual(self.post("/api/v1/competitions/", self._payload(), user=self.participant).status_code, 403)

    def test_create_organizer_returns_201_pending(self):
        resp = self.post("/api/v1/competitions/", self._payload(), user=self.organizer)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], Competition.Status.PENDING_APPROVAL)

    def test_create_admin_returns_201_approved(self):
        resp = self.post("/api/v1/competitions/", self._payload(), user=self.admin)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], Competition.Status.APPROVED)

    # --- PATCH update ---

    def test_update_anonymous_returns_401(self):
        self.assertEqual(
            self.patch(f"/api/v1/competitions/{self.approved.pk}", {"url_route": "http://x.com"}).status_code, 401
        )

    def test_update_guest_returns_403(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/competitions/{self.approved.pk}", {"url_route": "http://x.com"}, user=self.guest
            ).status_code,
            403,
        )

    def test_update_participant_returns_403(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/competitions/{self.approved.pk}", {"url_route": "http://x.com"}, user=self.participant
            ).status_code,
            403,
        )

    def test_update_non_owner_organizer_returns_403(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/competitions/{self.approved.pk}", {"url_route": "http://x.com"}, user=self.organizer
            ).status_code,
            403,
        )

    def test_update_owner_returns_200(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/competitions/{self.owned.pk}", {"url_route": "http://x.com"}, user=self.owner
            ).status_code,
            200,
        )

    def test_update_admin_returns_200(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/competitions/{self.approved.pk}", {"url_route": "http://x.com"}, user=self.admin
            ).status_code,
            200,
        )

    def test_update_is_hidden_by_owner_returns_403(self):
        self.assertEqual(
            self.patch(f"/api/v1/competitions/{self.owned.pk}", {"is_hidden": True}, user=self.owner).status_code, 403
        )

    def test_update_is_hidden_by_admin_returns_200(self):
        self.assertEqual(
            self.patch(f"/api/v1/competitions/{self.approved.pk}", {"is_hidden": True}, user=self.admin).status_code,
            200,
        )

    def test_update_participant_owner_returns_200(self):
        """PATCH checks ownership only - a participant who owns a competition in the DB can update it."""
        owned_by_par = _competition(submitted_by=self.participant)
        self.assertEqual(
            self.patch(
                f"/api/v1/competitions/{owned_by_par.pk}", {"url_route": "http://x.com"}, user=self.participant
            ).status_code,
            200,
        )

    # --- DELETE ---

    def test_delete_anonymous_returns_401(self):
        self.assertEqual(self.delete(f"/api/v1/competitions/{self.approved.pk}").status_code, 401)

    def test_delete_guest_returns_403(self):
        self.assertEqual(self.delete(f"/api/v1/competitions/{self.approved.pk}", user=self.guest).status_code, 403)

    def test_delete_participant_returns_403(self):
        self.assertEqual(
            self.delete(f"/api/v1/competitions/{self.approved.pk}", user=self.participant).status_code, 403
        )

    def test_delete_non_owner_organizer_returns_403(self):
        self.assertEqual(self.delete(f"/api/v1/competitions/{self.approved.pk}", user=self.organizer).status_code, 403)

    def test_delete_owner_returns_204(self):
        comp = _competition(submitted_by=self.owner)
        self.assertEqual(self.delete(f"/api/v1/competitions/{comp.pk}", user=self.owner).status_code, 204)

    def test_delete_admin_returns_204(self):
        comp = _competition()
        self.assertEqual(self.delete(f"/api/v1/competitions/{comp.pk}", user=self.admin).status_code, 204)


# ===========================================================================
# News article - locale via web form -> API + web view
# ===========================================================================


class NewsLocaleTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.admin = _user("nl_admin", role=User.Role.ADMIN)

    def test_article_created_via_web_form_has_all_locale_fields_in_api(self):
        from datetime import datetime as dt

        self.client.force_login(self.admin)
        self.client.post(
            "/news/articles/create/",
            {
                "title_ru": "Article RU",
                "title_kk": "Article KK",
                "title_en": "Article EN",
                "intro_ru": "Intro RU",
                "intro_kk": "Intro KK",
                "intro_en": "Intro EN",
                "body_ru": "",
                "body_kk": "",
                "body_en": "",
                "published_at": dt.now().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        article = NewsArticle.objects.filter(title_ru="Article RU").first()
        self.assertIsNotNone(article, "Article not created by web form")
        resp = self.get(f"/api/v1/news/{article.pk}", user=self.admin)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"]["ru"], "Article RU")
        self.assertEqual(data["title"]["kk"], "Article KK")
        self.assertEqual(data["title"]["en"], "Article EN")
        self.assertEqual(data["intro"]["ru"], "Intro RU")
        self.assertEqual(data["intro"]["kk"], "Intro KK")
        self.assertEqual(data["intro"]["en"], "Intro EN")

    def test_article_created_via_web_form_appears_in_api_list(self):
        from datetime import datetime as dt

        self.client.force_login(self.admin)
        self.client.post(
            "/news/articles/create/",
            {
                "title_ru": "List Article RU",
                "title_kk": "List Article KK",
                "title_en": "List Article EN",
                "intro_ru": "",
                "intro_kk": "",
                "intro_en": "",
                "body_ru": "",
                "body_kk": "",
                "body_en": "",
                "published_at": dt.now().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        article = NewsArticle.objects.filter(title_ru="List Article RU").first()
        self.assertIsNotNone(article)
        ids = [d["id"] for d in self.get("/api/v1/news/").json()]
        self.assertIn(article.pk, ids)

    def test_api_created_article_visible_in_web_view(self):
        article = _article()
        resp = self.client.get(f"/news/articles/{article.pk}/")
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# News - access control: every role x every endpoint
# ===========================================================================


class NewsAccessTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.guest = _user("na_guest", role=User.Role.GUEST)
        self.participant = _user("na_par", role=User.Role.PARTICIPANT)
        self.other = _user("na_other", role=User.Role.PARTICIPANT)
        self.admin = _user("na_admin", role=User.Role.ADMIN)
        self.article = _article()
        self.hidden_article = _article(is_hidden=True)
        self.draft = _draft(self.participant, submission_type=DraftSubmission.SubmissionType.NEWS)

    def _payload(self):
        return {"title": "T", "body": "B", "locale": "ru", "category": ""}

    # --- GET list (NewsArticle) ---

    def test_list_anonymous_sees_public_articles(self):
        resp = self.get("/api/v1/news/")
        self.assertEqual(resp.status_code, 200)
        ids = [d["id"] for d in resp.json()]
        self.assertIn(self.article.pk, ids)

    def test_list_anonymous_excludes_hidden(self):
        ids = [d["id"] for d in self.get("/api/v1/news/").json()]
        self.assertNotIn(self.hidden_article.pk, ids)

    def test_list_guest_excludes_hidden(self):
        ids = [d["id"] for d in self.get("/api/v1/news/", user=self.guest).json()]
        self.assertNotIn(self.hidden_article.pk, ids)

    def test_list_participant_excludes_hidden(self):
        ids = [d["id"] for d in self.get("/api/v1/news/", user=self.participant).json()]
        self.assertNotIn(self.hidden_article.pk, ids)

    def test_list_admin_includes_hidden(self):
        ids = [d["id"] for d in self.get("/api/v1/news/", user=self.admin).json()]
        self.assertIn(self.hidden_article.pk, ids)

    # --- GET detail (NewsArticle) ---

    def test_detail_anonymous_200_for_visible(self):
        self.assertEqual(self.get(f"/api/v1/news/{self.article.pk}").status_code, 200)

    def test_detail_anonymous_404_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/news/{self.hidden_article.pk}").status_code, 404)

    def test_detail_guest_404_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/news/{self.hidden_article.pk}", user=self.guest).status_code, 404)

    def test_detail_participant_404_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/news/{self.hidden_article.pk}", user=self.participant).status_code, 404)

    def test_detail_admin_200_for_hidden(self):
        self.assertEqual(self.get(f"/api/v1/news/{self.hidden_article.pk}", user=self.admin).status_code, 200)

    # --- POST create news draft ---

    def test_create_anonymous_returns_401(self):
        self.assertEqual(self.post("/api/v1/news/", self._payload()).status_code, 401)

    def test_create_guest_returns_403(self):
        self.assertEqual(self.post("/api/v1/news/", self._payload(), user=self.guest).status_code, 403)

    def test_create_participant_returns_201_pending(self):
        resp = self.post("/api/v1/news/", self._payload(), user=self.participant)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], DraftSubmission.Status.PENDING)

    def test_create_admin_returns_201_approved(self):
        resp = self.post("/api/v1/news/", self._payload(), user=self.admin)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], DraftSubmission.Status.APPROVED)

    # --- PATCH update news draft ---

    def test_update_anonymous_returns_401(self):
        self.assertEqual(self.patch(f"/api/v1/news/{self.draft.pk}", {"title": "X"}).status_code, 401)

    def test_update_guest_not_owner_returns_403(self):
        self.assertEqual(self.patch(f"/api/v1/news/{self.draft.pk}", {"title": "X"}, user=self.guest).status_code, 403)

    def test_update_author_returns_200(self):
        self.assertEqual(
            self.patch(f"/api/v1/news/{self.draft.pk}", {"title": "X"}, user=self.participant).status_code, 200
        )

    def test_update_other_participant_returns_403(self):
        self.assertEqual(self.patch(f"/api/v1/news/{self.draft.pk}", {"title": "X"}, user=self.other).status_code, 403)

    def test_update_admin_not_owner_returns_200(self):
        self.assertEqual(self.patch(f"/api/v1/news/{self.draft.pk}", {"title": "X"}, user=self.admin).status_code, 200)

    def test_update_approved_draft_returns_409(self):
        draft = _draft(self.participant, submission_type=DraftSubmission.SubmissionType.NEWS)
        draft.status = DraftSubmission.Status.APPROVED
        draft.save(update_fields=["status"])
        self.assertEqual(self.patch(f"/api/v1/news/{draft.pk}", {"title": "X"}, user=self.admin).status_code, 409)

    # --- DELETE news draft ---

    def test_delete_anonymous_returns_401(self):
        self.assertEqual(self.delete(f"/api/v1/news/{self.draft.pk}").status_code, 401)

    def test_delete_author_returns_204(self):
        d = _draft(self.participant, submission_type=DraftSubmission.SubmissionType.NEWS)
        self.assertEqual(self.delete(f"/api/v1/news/{d.pk}", user=self.participant).status_code, 204)

    def test_delete_other_participant_returns_403(self):
        self.assertEqual(self.delete(f"/api/v1/news/{self.draft.pk}", user=self.other).status_code, 403)

    def test_delete_admin_not_owner_returns_204(self):
        d = _draft(self.participant, submission_type=DraftSubmission.SubmissionType.NEWS)
        self.assertEqual(self.delete(f"/api/v1/news/{d.pk}", user=self.admin).status_code, 204)

    def test_delete_approved_draft_returns_409(self):
        draft = _draft(self.participant, submission_type=DraftSubmission.SubmissionType.NEWS)
        draft.status = DraftSubmission.Status.APPROVED
        draft.save(update_fields=["status"])
        self.assertEqual(self.delete(f"/api/v1/news/{draft.pk}", user=self.admin).status_code, 409)


# ===========================================================================
# Knowledge - locale CRUD + web form -> API
# ===========================================================================


class KnowledgeLocaleCRUDTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.admin = _user("kl_admin", role=User.Role.ADMIN)
        self.author = _user("kl_author", role=User.Role.PARTICIPANT)

    def _create(self, user=None, **overrides):
        payload = {"title": "Knowledge Title", "body": "Body text", "locale": "ru", "category": ""}
        payload.update(overrides)
        resp = self.post("/api/v1/knowledge/", payload, user=user or self.admin)
        self.assertEqual(resp.status_code, 201)
        return resp.json()

    def test_create_returns_all_fields(self):
        data = self._create()
        self.assertEqual(data["title"], "Knowledge Title")
        self.assertEqual(data["body"], "Body text")
        self.assertEqual(data["locale"], "ru")

    def test_all_locales_accepted(self):
        for locale in ("ru", "kk", "en"):
            data = self._create(locale=locale, title=f"Title {locale}")
            self.assertEqual(data["locale"], locale)

    def test_approved_draft_visible_to_anonymous(self):
        data = self._create()
        resp = self.get(f"/api/v1/knowledge/{data['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Knowledge Title")

    def test_pending_draft_visible_to_author(self):
        data = self._create(user=self.author)
        resp = self.get(f"/api/v1/knowledge/{data['id']}", user=self.author)
        self.assertEqual(resp.status_code, 200)

    def test_approved_drafts_appear_in_list(self):
        data = self._create()
        ids = [d["id"] for d in self.get("/api/v1/knowledge/").json()]
        self.assertIn(data["id"], ids)

    def test_patch_updates_title(self):
        data = self._create(user=self.author)
        pk = data["id"]
        self.patch(f"/api/v1/knowledge/{pk}", {"title": "Updated"}, user=self.author)
        resp = self.get(f"/api/v1/knowledge/{pk}", user=self.author)
        self.assertEqual(resp.json()["title"], "Updated")

    def test_patch_updates_locale(self):
        data = self._create(user=self.author)
        pk = data["id"]
        self.patch(f"/api/v1/knowledge/{pk}", {"locale": "kk"}, user=self.author)
        self.assertEqual(self.get(f"/api/v1/knowledge/{pk}", user=self.author).json()["locale"], "kk")

    def test_delete_removes_draft(self):
        data = self._create(user=self.author)
        pk = data["id"]
        self.delete(f"/api/v1/knowledge/{pk}", user=self.author)
        self.assertEqual(self.get(f"/api/v1/knowledge/{pk}", user=self.author).status_code, 404)

    def test_web_form_creates_draft_visible_via_api(self):
        participant = _user("kl_wf_par", role=User.Role.PARTICIPANT)
        self.client.force_login(participant)
        self.client.post(
            "/knowledge/submit/",
            {"title": "Web Draft", "body": "Web body", "locale": "ru", "category": ""},
        )
        draft = DraftSubmission.objects.filter(title="Web Draft", author=participant).first()
        self.assertIsNotNone(draft, "Draft not created via web form")
        resp = self.get(f"/api/v1/knowledge/{draft.pk}", user=participant)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Web Draft")


# ===========================================================================
# Knowledge - access control: every role x every endpoint
# ===========================================================================


class KnowledgeAccessTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.guest = _user("ka_guest", role=User.Role.GUEST)
        self.author = _user("ka_author", role=User.Role.PARTICIPANT)
        self.other = _user("ka_other", role=User.Role.PARTICIPANT)
        self.admin = _user("ka_admin", role=User.Role.ADMIN)
        self.approved_draft = _draft(
            self.author,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            status=DraftSubmission.Status.APPROVED,
        )
        self.pending_draft = _draft(
            self.author,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
        )

    def _payload(self):
        return {"title": "T", "body": "B", "locale": "ru", "category": ""}

    # --- GET list ---

    def test_list_anonymous_sees_approved(self):
        resp = self.get("/api/v1/knowledge/")
        self.assertEqual(resp.status_code, 200)
        ids = [d["id"] for d in resp.json()]
        self.assertIn(self.approved_draft.pk, ids)

    def test_list_anonymous_no_pending(self):
        ids = [d["id"] for d in self.get("/api/v1/knowledge/").json()]
        self.assertNotIn(self.pending_draft.pk, ids)

    def test_list_pending_anonymous_returns_401(self):
        self.assertEqual(self.get("/api/v1/knowledge/?status=pending").status_code, 401)

    def test_list_pending_non_admin_sees_only_own(self):
        resp = self.get("/api/v1/knowledge/?status=pending", user=self.author)
        ids = [d["id"] for d in resp.json()]
        self.assertIn(self.pending_draft.pk, ids)

    def test_list_pending_non_admin_does_not_see_others(self):
        resp = self.get("/api/v1/knowledge/?status=pending", user=self.other)
        ids = [d["id"] for d in resp.json()]
        self.assertNotIn(self.pending_draft.pk, ids)

    def test_list_pending_admin_sees_all(self):
        resp = self.get("/api/v1/knowledge/?status=pending", user=self.admin)
        ids = [d["id"] for d in resp.json()]
        self.assertIn(self.pending_draft.pk, ids)

    # --- GET detail ---

    def test_detail_anonymous_200_for_approved(self):
        self.assertEqual(self.get(f"/api/v1/knowledge/{self.approved_draft.pk}").status_code, 200)

    def test_detail_anonymous_404_for_pending(self):
        self.assertEqual(self.get(f"/api/v1/knowledge/{self.pending_draft.pk}").status_code, 404)

    def test_detail_author_200_for_own_pending(self):
        self.assertEqual(self.get(f"/api/v1/knowledge/{self.pending_draft.pk}", user=self.author).status_code, 200)

    def test_detail_other_participant_403_for_pending(self):
        self.assertEqual(self.get(f"/api/v1/knowledge/{self.pending_draft.pk}", user=self.other).status_code, 403)

    def test_detail_admin_200_for_pending(self):
        self.assertEqual(self.get(f"/api/v1/knowledge/{self.pending_draft.pk}", user=self.admin).status_code, 200)

    # --- POST create ---

    def test_create_anonymous_returns_401(self):
        self.assertEqual(self.post("/api/v1/knowledge/", self._payload()).status_code, 401)

    def test_create_guest_returns_403(self):
        self.assertEqual(self.post("/api/v1/knowledge/", self._payload(), user=self.guest).status_code, 403)

    def test_create_participant_returns_201_pending(self):
        resp = self.post("/api/v1/knowledge/", self._payload(), user=self.author)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], DraftSubmission.Status.PENDING)

    def test_create_admin_returns_201_approved(self):
        resp = self.post("/api/v1/knowledge/", self._payload(), user=self.admin)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], DraftSubmission.Status.APPROVED)

    # --- PATCH update ---

    def test_update_anonymous_returns_401(self):
        self.assertEqual(self.patch(f"/api/v1/knowledge/{self.pending_draft.pk}", {"title": "X"}).status_code, 401)

    def test_update_guest_not_owner_returns_403(self):
        self.assertEqual(
            self.patch(f"/api/v1/knowledge/{self.pending_draft.pk}", {"title": "X"}, user=self.guest).status_code, 403
        )

    def test_update_author_returns_200(self):
        self.assertEqual(
            self.patch(f"/api/v1/knowledge/{self.pending_draft.pk}", {"title": "X"}, user=self.author).status_code, 200
        )

    def test_update_other_participant_returns_403(self):
        self.assertEqual(
            self.patch(f"/api/v1/knowledge/{self.pending_draft.pk}", {"title": "X"}, user=self.other).status_code, 403
        )

    def test_update_admin_not_owner_returns_200(self):
        self.assertEqual(
            self.patch(f"/api/v1/knowledge/{self.pending_draft.pk}", {"title": "X"}, user=self.admin).status_code, 200
        )

    def test_update_approved_draft_returns_409(self):
        self.assertEqual(
            self.patch(f"/api/v1/knowledge/{self.approved_draft.pk}", {"title": "X"}, user=self.author).status_code, 409
        )

    def test_update_approved_draft_by_admin_returns_409(self):
        self.assertEqual(
            self.patch(f"/api/v1/knowledge/{self.approved_draft.pk}", {"title": "X"}, user=self.admin).status_code, 409
        )

    # --- DELETE ---

    def test_delete_anonymous_returns_401(self):
        self.assertEqual(self.delete(f"/api/v1/knowledge/{self.pending_draft.pk}").status_code, 401)

    def test_delete_author_returns_204(self):
        d = _draft(self.author, submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        self.assertEqual(self.delete(f"/api/v1/knowledge/{d.pk}", user=self.author).status_code, 204)

    def test_delete_other_participant_returns_403(self):
        self.assertEqual(self.delete(f"/api/v1/knowledge/{self.pending_draft.pk}", user=self.other).status_code, 403)

    def test_delete_admin_not_owner_returns_204(self):
        d = _draft(self.author, submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        self.assertEqual(self.delete(f"/api/v1/knowledge/{d.pk}", user=self.admin).status_code, 204)

    def test_delete_approved_draft_returns_409(self):
        self.assertEqual(self.delete(f"/api/v1/knowledge/{self.approved_draft.pk}", user=self.admin).status_code, 409)


# ===========================================================================
# Location - access control: every role x every endpoint
# ===========================================================================


class LocationAccessTest(TestCase, ApiTestMixin):
    def setUp(self):
        self.guest = _user("la_guest", role=User.Role.GUEST)
        self.participant = _user("la_par", role=User.Role.PARTICIPANT)
        self.organizer = _user("la_org", role=User.Role.ORGANIZER)
        self.admin = _user("la_admin", role=User.Role.ADMIN)
        self.loc = _location()

    def _create_payload(self):
        return {"name": {"ru": "Loc RU", "kk": "Loc KK", "en": "Loc EN"}}

    # --- GET list (all can read) ---

    def test_list_anonymous_returns_200(self):
        self.assertEqual(self.get("/api/v1/locations/").status_code, 200)

    def test_list_guest_returns_200(self):
        self.assertEqual(self.get("/api/v1/locations/", user=self.guest).status_code, 200)

    def test_list_participant_returns_200(self):
        self.assertEqual(self.get("/api/v1/locations/", user=self.participant).status_code, 200)

    # --- GET detail (all can read) ---

    def test_detail_anonymous_returns_200(self):
        self.assertEqual(self.get(f"/api/v1/locations/{self.loc.pk}").status_code, 200)

    def test_detail_participant_returns_200(self):
        self.assertEqual(self.get(f"/api/v1/locations/{self.loc.pk}", user=self.participant).status_code, 200)

    # --- POST create (ADMIN only) ---

    def test_create_anonymous_returns_401(self):
        self.assertEqual(self.post("/api/v1/locations/", self._create_payload()).status_code, 401)

    def test_create_guest_returns_403(self):
        self.assertEqual(self.post("/api/v1/locations/", self._create_payload(), user=self.guest).status_code, 403)

    def test_create_participant_returns_403(self):
        self.assertEqual(
            self.post("/api/v1/locations/", self._create_payload(), user=self.participant).status_code, 403
        )

    def test_create_organizer_returns_403(self):
        self.assertEqual(self.post("/api/v1/locations/", self._create_payload(), user=self.organizer).status_code, 403)

    def test_create_admin_returns_201(self):
        resp = self.post("/api/v1/locations/", self._create_payload(), user=self.admin)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"]["ru"], "Loc RU")
        self.assertEqual(data["name"]["kk"], "Loc KK")
        self.assertEqual(data["name"]["en"], "Loc EN")

    # --- PATCH update (ADMIN only) ---

    def test_update_anonymous_returns_401(self):
        self.assertEqual(
            self.patch(f"/api/v1/locations/{self.loc.pk}", {"name": {"ru": "X", "kk": "", "en": ""}}).status_code, 401
        )

    def test_update_guest_returns_403(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/locations/{self.loc.pk}", {"name": {"ru": "X", "kk": "", "en": ""}}, user=self.guest
            ).status_code,
            403,
        )

    def test_update_participant_returns_403(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/locations/{self.loc.pk}", {"name": {"ru": "X", "kk": "", "en": ""}}, user=self.participant
            ).status_code,
            403,
        )

    def test_update_organizer_returns_403(self):
        self.assertEqual(
            self.patch(
                f"/api/v1/locations/{self.loc.pk}", {"name": {"ru": "X", "kk": "", "en": ""}}, user=self.organizer
            ).status_code,
            403,
        )

    def test_update_admin_returns_200(self):
        resp = self.patch(
            f"/api/v1/locations/{self.loc.pk}",
            {"name": {"ru": "New RU", "kk": "New KK", "en": "New EN"}},
            user=self.admin,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"]["ru"], "New RU")
        self.assertEqual(data["name"]["kk"], "New KK")
        self.assertEqual(data["name"]["en"], "New EN")

    # --- DELETE (ADMIN only) ---

    def test_delete_anonymous_returns_401(self):
        self.assertEqual(self.delete(f"/api/v1/locations/{self.loc.pk}").status_code, 401)

    def test_delete_guest_returns_403(self):
        loc = _location()
        self.assertEqual(self.delete(f"/api/v1/locations/{loc.pk}", user=self.guest).status_code, 403)

    def test_delete_participant_returns_403(self):
        loc = _location()
        self.assertEqual(self.delete(f"/api/v1/locations/{loc.pk}", user=self.participant).status_code, 403)

    def test_delete_organizer_returns_403(self):
        loc = _location()
        self.assertEqual(self.delete(f"/api/v1/locations/{loc.pk}", user=self.organizer).status_code, 403)

    def test_delete_admin_returns_204(self):
        loc = _location()
        self.assertEqual(self.delete(f"/api/v1/locations/{loc.pk}", user=self.admin).status_code, 204)
