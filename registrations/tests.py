import datetime
import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Competition
from registrations.models import (
    CompetitionRegistration,
    RegistrationCategory,
    Team,
    check_duplicate,
)


def make_user(username, role=User.Role.PARTICIPANT, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="Pass123!",
        role=role,
        **kwargs,
    )


def make_competition(title="Test Race", status=Competition.Status.APPROVED, **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": datetime.date(2026, 7, 1),
        "status": status,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def make_open_competition(**kwargs):
    defaults = {
        "registration_enabled": True,
        "registration_mode": "free",
        "birth_date_mode": "year",
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return make_competition(**defaults)


def make_category(competition, name="Elite", **kwargs):
    defaults = {"male": True, "female": True}
    defaults.update(kwargs)
    return RegistrationCategory.objects.create(competition=competition, name=name, **defaults)


def make_registration(competition, **kwargs):
    defaults = {
        "first_name": "Test",
        "last_name": "User",
        "birth_date": datetime.date(1990, 1, 1),
        "gender": "M",
    }
    defaults.update(kwargs)
    return CompetitionRegistration.objects.create(competition=competition, **defaults)


class TeamModelTests(TestCase):
    def test_get_or_restore_creates_new(self):
        team = Team.get_or_restore("Rockets")
        self.assertEqual(team.name, "Rockets")
        self.assertFalse(team.is_deleted)

    def test_get_or_restore_returns_existing(self):
        t1 = Team.objects.create(name="Eagles")
        t2 = Team.get_or_restore("Eagles")
        self.assertEqual(t1.pk, t2.pk)

    def test_get_or_restore_case_insensitive(self):
        t1 = Team.objects.create(name="tigers")
        t2 = Team.get_or_restore("Tigers")
        self.assertEqual(t1.pk, t2.pk)

    def test_get_or_restore_restores_deleted(self):
        team = Team.objects.create(name="Wolves", is_deleted=True)
        restored = Team.get_or_restore("Wolves")
        self.assertEqual(team.pk, restored.pk)
        restored.refresh_from_db()
        self.assertFalse(restored.is_deleted)

    def test_autocomplete_excludes_deleted(self):
        Team.objects.create(name="Active Team", is_deleted=False)
        Team.objects.create(name="Deleted Team", is_deleted=True)
        self.client.force_login(make_user("ac_user"))
        response = self.client.get(reverse("registrations:team_autocomplete"))
        data = json.loads(response.content)
        names = [r["name"] for r in data["results"]]
        self.assertIn("Active Team", names)
        self.assertNotIn("Deleted Team", names)

    def test_existing_registration_retains_team_after_soft_delete(self):
        comp = make_competition()
        team = Team.objects.create(name="OldTeam")
        reg = make_registration(comp, team=team)
        team.is_deleted = True
        team.save()
        reg.refresh_from_db()
        self.assertIsNotNone(reg.team)
        self.assertEqual(reg.team.name, "OldTeam")

    def test_city_autocomplete_excludes_pending_competition_cities(self):
        pending_comp = make_competition(title="Pending", status=Competition.Status.PENDING_APPROVAL)
        make_registration(pending_comp, city="SecretCity")
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertNotIn("SecretCity", cities)

    def test_city_autocomplete_excludes_hidden_competition_cities(self):
        hidden_comp = make_competition(title="Hidden", is_hidden=True)
        make_registration(hidden_comp, city="HiddenCity")
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertNotIn("HiddenCity", cities)

    def test_city_autocomplete_includes_approved_competition_cities(self):
        approved_comp = make_competition(title="Approved Race")
        make_registration(approved_comp, city="PublicCity")
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertIn("PublicCity", cities)

    def test_city_autocomplete_excludes_deleted_competition_cities(self):
        deleted_comp = make_competition(title="Deleted Race", is_deleted=True)
        make_registration(deleted_comp, city="DeletedCompCity")
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertNotIn("DeletedCompCity", cities)

    def test_city_autocomplete_excludes_rejected_registration_cities(self):
        comp = make_competition(title="Active Race")
        make_registration(comp, city="RejectedCity", is_rejected=True)
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertNotIn("RejectedCity", cities)

    def test_city_autocomplete_excludes_unapproved_city_when_approval_required(self):
        comp = make_competition(title="Approval Race", require_approval=True)
        make_registration(comp, city="UnapprovedCity", is_approved=False)
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertNotIn("UnapprovedCity", cities)

    def test_city_autocomplete_excludes_unpaid_city_when_payment_required(self):
        comp = make_competition(title="Payment Race", require_payment=True)
        make_registration(comp, city="UnpaidCity", is_paid=False)
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertNotIn("UnpaidCity", cities)

    def test_city_autocomplete_includes_approved_paid_city(self):
        comp = make_competition(title="Full Race", require_approval=True, require_payment=True)
        make_registration(comp, city="ApprovedPaidCity", is_approved=True, is_paid=True)
        response = self.client.get(reverse("registrations:city_autocomplete"))
        data = json.loads(response.content)
        cities = [r["name"] for r in data["results"]]
        self.assertIn("ApprovedPaidCity", cities)


class RegistrationCategoryMatchesTests(TestCase):
    def setUp(self):
        self.comp = make_competition()

    def test_matches_male_only_category(self):
        cat = make_category(self.comp, male=True, female=False)
        bd = datetime.date(1990, 1, 1)
        self.assertTrue(cat.matches("M", bd))
        self.assertFalse(cat.matches("F", bd))

    def test_matches_female_only_category(self):
        cat = make_category(self.comp, male=False, female=True)
        bd = datetime.date(1990, 1, 1)
        self.assertTrue(cat.matches("F", bd))
        self.assertFalse(cat.matches("M", bd))

    def test_matches_birth_date_in_range(self):
        cat = make_category(
            self.comp,
            birth_from=datetime.date(1980, 1, 1),
            birth_to=datetime.date(1999, 12, 31),
        )
        self.assertTrue(cat.matches("M", datetime.date(1990, 6, 15)))
        self.assertFalse(cat.matches("M", datetime.date(2000, 1, 1)))
        self.assertFalse(cat.matches("M", datetime.date(1979, 12, 31)))

    def test_matches_null_bounds_always_true(self):
        cat = make_category(self.comp, birth_from=None, birth_to=None)
        self.assertTrue(cat.matches("M", datetime.date(1950, 1, 1)))
        self.assertTrue(cat.matches("F", datetime.date(2005, 1, 1)))

    def test_matches_null_from_open_below(self):
        cat = make_category(self.comp, birth_from=None, birth_to=datetime.date(1999, 12, 31))
        self.assertTrue(cat.matches("M", datetime.date(1950, 1, 1)))
        self.assertFalse(cat.matches("M", datetime.date(2000, 6, 1)))

    def test_matches_boundaries_are_inclusive(self):
        # A "2020-2025" year category (birth_from = Jan 1 2020, birth_to = Dec 31 2025) must accept
        # both ends inclusively: a 2020-born and a 2025-born are eligible, 2019/2026 are not.
        cat = make_category(
            self.comp,
            birth_from=datetime.date(2020, 1, 1),
            birth_to=datetime.date(2025, 12, 31),
        )
        self.assertTrue(cat.matches("F", datetime.date(2020, 1, 1)))  # lower boundary
        self.assertTrue(cat.matches("F", datetime.date(2025, 12, 31)))  # upper boundary
        self.assertTrue(cat.matches("F", datetime.date(2025, 6, 15)))
        self.assertFalse(cat.matches("F", datetime.date(2019, 12, 31)))
        self.assertFalse(cat.matches("F", datetime.date(2026, 1, 1)))


class CheckDuplicateTests(TestCase):
    def setUp(self):
        self.user = make_user("dupuser")
        self.comp = make_competition(registration_mode="self_only")

    def test_self_only_no_duplicate_initially(self):
        self.assertFalse(check_duplicate(self.comp, self.user, "A", "B", datetime.date(1990, 1, 1)))

    def test_self_only_duplicate_by_user(self):
        make_registration(self.comp, user=self.user)
        self.assertTrue(check_duplicate(self.comp, self.user, "A", "B", datetime.date(1990, 1, 1)))

    def test_self_only_ignores_allow_multiple_registrations(self):
        # allow_multiple_registrations has no effect in self_only mode
        self.comp.allow_multiple_registrations = True
        self.comp.save()
        make_registration(self.comp, user=self.user)
        self.assertTrue(check_duplicate(self.comp, self.user, "A", "B", datetime.date(1990, 1, 1)))

    def test_free_duplicate_by_name_and_year(self):
        self.comp.registration_mode = "free"
        self.comp.save()
        make_registration(self.comp, first_name="Ivan", last_name="Petrov", birth_date=datetime.date(1990, 6, 1))
        self.assertTrue(check_duplicate(self.comp, None, "Ivan", "Petrov", datetime.date(1990, 3, 15)))

    def test_free_no_duplicate_different_year(self):
        self.comp.registration_mode = "free"
        self.comp.save()
        make_registration(self.comp, first_name="Ivan", last_name="Petrov", birth_date=datetime.date(1990, 6, 1))
        self.assertFalse(check_duplicate(self.comp, None, "Ivan", "Petrov", datetime.date(1991, 3, 15)))

    def test_free_name_check_is_case_insensitive(self):
        self.comp.registration_mode = "free"
        self.comp.save()
        make_registration(self.comp, first_name="ivan", last_name="petrov", birth_date=datetime.date(1990, 1, 1))
        self.assertTrue(check_duplicate(self.comp, None, "IVAN", "PETROV", datetime.date(1990, 5, 5)))


class RegisterForCompetitionViewTests(TestCase):
    def setUp(self):
        self.user = make_user("reguser", gender="M", birth_date=datetime.date(1990, 1, 1))
        self.comp = make_open_competition()
        self.url = reverse("registrations:register", args=[self.comp.pk])

    def test_get_shows_form(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_birth_date_prefilled_as_iso_under_ru_locale(self):
        # Regression: a date-mode competition pre-fills the user's birth_date; ru-locale L10N
        # rendered it localized, which <input type=date> rejects. It must be ISO YYYY-MM-DD.
        import re

        comp = make_open_competition(birth_date_mode="date")
        self.client.force_login(self.user)  # self.user.birth_date == 1990-01-01
        resp = self.client.get(reverse("registrations:register", args=[comp.pk]), HTTP_ACCEPT_LANGUAGE="ru")
        m = re.search(r'name="birth_date"[^>]*value="([^"]*)"', resp.content.decode())
        self.assertEqual(m.group(1), "1990-01-01")

    def test_anonymous_redirected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_registration_closed_when_disabled(self):
        self.comp.registration_enabled = False
        self.comp.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["registration_closed"])

    def test_registration_closed_after_deadline(self):
        self.comp.registration_deadline = datetime.date(2020, 1, 1)
        self.comp.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertTrue(response.context["registration_closed"])

    def test_post_creates_registration(self):
        self.client.force_login(self.user)
        cat = make_category(self.comp)
        response = self.client.post(
            self.url,
            {
                "first_name": "Denis",
                "last_name": "Test",
                "gender": "M",
                "birth_year": 1990,
                "category": cat.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        reg = CompetitionRegistration.objects.get(competition=self.comp, first_name="Denis", last_name="Test")
        self.assertEqual(reg.user, self.user)

    def test_self_only_requires_profile_complete(self):
        user_incomplete = make_user("incomplete")
        comp = make_open_competition(registration_mode="self_only")
        self.client.force_login(user_incomplete)
        response = self.client.post(
            reverse("registrations:register", args=[comp.pk]),
            {
                "birth_year": 1990,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_auto_approved_when_approval_not_required(self):
        self.client.force_login(self.user)
        cat = make_category(self.comp)
        self.client.post(
            self.url, {"first_name": "Denis", "last_name": "T", "gender": "M", "birth_year": 1990, "category": cat.pk}
        )
        reg = CompetitionRegistration.objects.get(competition=self.comp)
        self.assertTrue(reg.is_approved)

    def test_not_auto_approved_when_approval_required(self):
        comp = make_open_competition(require_approval=True)
        self.client.force_login(self.user)
        cat = make_category(comp)
        self.client.post(
            reverse("registrations:register", args=[comp.pk]),
            {"first_name": "Denis", "last_name": "T", "gender": "M", "birth_year": 1990, "category": cat.pk},
        )
        reg = CompetitionRegistration.objects.get(competition=comp)
        self.assertFalse(reg.is_approved)

    def test_auto_paid_when_payment_not_required(self):
        self.client.force_login(self.user)
        cat = make_category(self.comp)
        self.client.post(
            self.url, {"first_name": "Denis", "last_name": "T", "gender": "M", "birth_year": 1990, "category": cat.pk}
        )
        reg = CompetitionRegistration.objects.get(competition=self.comp)
        self.assertTrue(reg.is_paid)

    def test_not_auto_paid_when_payment_required(self):
        comp = make_open_competition(require_payment=True)
        self.client.force_login(self.user)
        cat = make_category(comp)
        self.client.post(
            reverse("registrations:register", args=[comp.pk]),
            {"first_name": "Denis", "last_name": "T", "gender": "M", "birth_year": 1990, "category": cat.pk},
        )
        reg = CompetitionRegistration.objects.get(competition=comp)
        self.assertFalse(reg.is_paid)

    def test_duplicate_registration_rejected(self):
        self.client.force_login(self.user)
        cat = make_category(self.comp)
        self.client.post(
            self.url,
            {
                "first_name": "Denis",
                "last_name": "Test",
                "gender": "M",
                "birth_year": 1990,
                "category": cat.pk,
            },
        )
        response = self.client.post(
            self.url,
            {
                "first_name": "Denis",
                "last_name": "Test",
                "gender": "M",
                "birth_year": 1990,
                "category": cat.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CompetitionRegistration.objects.filter(competition=self.comp).count(), 1)

    def test_pending_competition_register_returns_404(self):
        pending_comp = make_open_competition(status=Competition.Status.PENDING_APPROVAL)
        url = reverse("registrations:register", args=[pending_comp.pk])
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_registration_rejected_when_limit_already_reached(self):
        comp = make_open_competition(max_participants=1)
        make_registration(comp)
        url = reverse("registrations:register", args=[comp.pk])
        self.client.force_login(self.user)
        response = self.client.post(
            url,
            {"first_name": "New", "last_name": "Person", "gender": "M", "birth_year": 1990},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CompetitionRegistration.objects.filter(competition=comp).count(), 1)


class ParticipantListViewTests(TestCase):
    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER)
        self.comp = make_competition(submitted_by=self.organizer, registration_enabled=True)
        self.url = reverse("registrations:participant_list", args=[self.comp.pk])

    def test_anonymous_can_view_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_manager_sees_all_registrations(self):
        make_registration(self.comp, is_rejected=True)
        make_registration(self.comp, first_name="Bob")
        self.client.force_login(self.organizer)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["registrations"]), 2)
        self.assertTrue(response.context["is_manager"])

    def test_public_hides_rejected(self):
        make_registration(self.comp, is_rejected=True)
        make_registration(self.comp, first_name="Visible")
        response = self.client.get(self.url)
        regs = list(response.context["registrations"])
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0].first_name, "Visible")

    def test_require_approval_hides_unapproved_in_public(self):
        self.comp.require_approval = True
        self.comp.save()
        make_registration(self.comp, is_approved=True)
        make_registration(self.comp, is_approved=False)
        response = self.client.get(self.url)
        regs = list(response.context["registrations"])
        self.assertEqual(len(regs), 1)
        self.assertTrue(regs[0].is_approved)

    def test_pending_competition_participant_list_returns_404(self):
        pending_comp = make_competition(title="Pending Race", status=Competition.Status.PENDING_APPROVAL)
        url = reverse("registrations:participant_list", args=[pending_comp.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_pending_competition_participant_list_accessible_to_manager(self):
        pending_comp = make_competition(
            title="Manager Pending", status=Competition.Status.PENDING_APPROVAL, submitted_by=self.organizer
        )
        url = reverse("registrations:participant_list", args=[pending_comp.pk])
        self.client.force_login(self.organizer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class ManagementActionTests(TestCase):
    def setUp(self):
        self.organizer = make_user("mgr", role=User.Role.ORGANIZER)
        self.other = make_user("other", role=User.Role.PARTICIPANT)
        self.comp = make_competition(submitted_by=self.organizer, registration_mode="free")
        self.reg = make_registration(self.comp)
        self.client.force_login(self.organizer)

    def test_approve_sets_flag(self):
        url = reverse("registrations:approve", args=[self.comp.pk, self.reg.pk])
        self.client.post(url)
        self.reg.refresh_from_db()
        self.assertTrue(self.reg.is_approved)
        self.assertFalse(self.reg.is_rejected)

    def test_reject_sets_flag_and_note(self):
        url = reverse("registrations:reject", args=[self.comp.pk, self.reg.pk])
        self.client.post(url, {"rejection_note": "Missing docs"})
        self.reg.refresh_from_db()
        self.assertTrue(self.reg.is_rejected)
        self.assertFalse(self.reg.is_approved)
        self.assertEqual(self.reg.rejection_note, "Missing docs")

    def test_mark_paid_sets_flag(self):
        url = reverse("registrations:mark_paid", args=[self.comp.pk, self.reg.pk])
        self.client.post(url)
        self.reg.refresh_from_db()
        self.assertTrue(self.reg.is_paid)

    def test_delete_removes_registration(self):
        url = reverse("registrations:delete_registration", args=[self.comp.pk, self.reg.pk])
        self.client.post(url)
        self.assertFalse(CompetitionRegistration.objects.filter(pk=self.reg.pk).exists())

    def test_non_manager_cannot_approve(self):
        self.client.force_login(self.other)
        url = reverse("registrations:approve", args=[self.comp.pk, self.reg.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_manual_add_in_free_mode(self):
        url = reverse("registrations:manual_add", args=[self.comp.pk])
        response = self.client.post(
            url,
            {
                "first_name": "Manual",
                "last_name": "Add",
                "gender": "M",
                "birth_year": 1990,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CompetitionRegistration.objects.filter(competition=self.comp, first_name="Manual").exists())

    def test_manual_add_blocked_in_self_only_mode(self):
        self.comp.registration_mode = "self_only"
        self.comp.save()
        url = reverse("registrations:manual_add", args=[self.comp.pk])
        response = self.client.post(
            url,
            {
                "first_name": "Manual",
                "last_name": "Add",
                "gender": "M",
                "birth_year": 1990,
            },
        )
        self.assertEqual(response.status_code, 403)


class EditRegistrationViewTests(TestCase):
    def setUp(self):
        self.organizer = make_user("editmgr", role=User.Role.ORGANIZER)
        self.comp_self = make_competition(submitted_by=self.organizer, registration_mode="self_only")
        self.comp_free = make_competition(title="Free Race", submitted_by=self.organizer, registration_mode="free")
        self.reg_self = make_registration(self.comp_self)
        self.reg_free = make_registration(self.comp_free)
        self.client.force_login(self.organizer)

    def test_edit_self_only_keeps_service_fields_only(self):
        url = reverse("registrations:edit_registration", args=[self.comp_self.pk, self.reg_self.pk])
        response = self.client.post(url, {"is_approved": "on", "is_paid": "on"})
        self.assertEqual(response.status_code, 302)
        self.reg_self.refresh_from_db()
        self.assertTrue(self.reg_self.is_approved)
        self.assertTrue(self.reg_self.is_paid)

    def test_edit_free_mode_updates_all_fields(self):
        url = reverse("registrations:edit_registration", args=[self.comp_free.pk, self.reg_free.pk])
        response = self.client.post(
            url,
            {
                "first_name": "Updated",
                "last_name": "Name",
                "birth_date": "1995-05-05",
                "gender": "F",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.reg_free.refresh_from_db()
        self.assertEqual(self.reg_free.first_name, "Updated")
        self.assertEqual(self.reg_free.gender, "F")

    def test_xss_payload_in_relay_fields_is_escaped_on_save(self):
        relay_reg = make_registration(
            self.comp_free,
            participant_names="Rider One<BR>Rider Two",
            participant_birth_years="1990<BR>1995",
            participant_cities="City A<BR>City B",
        )
        url = reverse("registrations:edit_registration", args=[self.comp_free.pk, relay_reg.pk])
        self.client.post(
            url,
            {
                "first_name": "",
                "last_name": "",
                "birth_date": "1990-01-01",
                "gender": "M",
                "participant_names": "<script>alert(1)</script><BR>Rider Two",
                "participant_birth_years": "<img src=x><BR>1995",
                "participant_cities": "<b>City A</b><BR>City B",
            },
        )
        relay_reg.refresh_from_db()
        self.assertNotIn("<script>", relay_reg.participant_names)
        self.assertNotIn("<img", relay_reg.participant_birth_years)
        self.assertNotIn("<b>", relay_reg.participant_cities)

    def test_relay_xss_not_rendered_as_html_in_participant_list(self):
        relay_reg = make_registration(
            self.comp_free,
            participant_names="Rider One<BR>Rider Two",
        )
        url_edit = reverse("registrations:edit_registration", args=[self.comp_free.pk, relay_reg.pk])
        self.client.post(
            url_edit,
            {
                "first_name": "",
                "last_name": "",
                "birth_date": "1990-01-01",
                "gender": "M",
                "participant_names": "<script>xss</script><BR>Rider Two",
            },
        )
        url_list = reverse("registrations:participant_list", args=[self.comp_free.pk])
        resp = self.client.get(url_list)
        self.assertNotIn(b"<script>xss</script>", resp.content)


class ParticipantsAPIViewTests(TestCase):
    def setUp(self):
        self.comp = make_competition(
            registration_enabled=True,
            registration_mode="free",
        )
        self.token = str(self.comp.upload_token)
        self.url = "/api/v1/participants/"

    def test_missing_token_returns_422(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 422)

    def test_invalid_token_returns_401(self):
        response = self.client.get(self.url, {"competition_token": "00000000-0000-0000-0000-000000000000"})
        self.assertEqual(response.status_code, 401)

    def test_valid_token_returns_200(self):
        response = self.client.get(self.url, {"competition_token": self.token})
        self.assertEqual(response.status_code, 200)

    def test_response_structure(self):
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        self.assertIn("participants", data)
        self.assertIn("categories", data)
        self.assertIn("require_approval", data)
        self.assertIn("require_payment", data)

    def test_rejected_excluded_from_response(self):
        make_registration(self.comp, first_name="Rejected", is_rejected=True)
        make_registration(self.comp, first_name="Valid")
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        names = [p["first_name"] for p in data["participants"]]
        self.assertNotIn("Rejected", names)
        self.assertIn("Valid", names)

    def test_require_approval_filters_unapproved(self):
        self.comp.require_approval = True
        self.comp.save()
        make_registration(self.comp, first_name="Approved", is_approved=True)
        make_registration(self.comp, first_name="Pending", is_approved=False)
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        names = [p["first_name"] for p in data["participants"]]
        self.assertIn("Approved", names)
        self.assertNotIn("Pending", names)

    def test_require_payment_filters_unpaid(self):
        self.comp.require_payment = True
        self.comp.save()
        make_registration(self.comp, first_name="Paid", is_paid=True)
        make_registration(self.comp, first_name="Unpaid", is_paid=False)
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        names = [p["first_name"] for p in data["participants"]]
        self.assertIn("Paid", names)
        self.assertNotIn("Unpaid", names)

    def test_category_id_in_participant_json(self):
        cat = make_category(self.comp)
        make_registration(self.comp, category=cat)
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        self.assertIn("category_id", data["participants"][0])

    def test_soft_deleted_category_included_if_referenced(self):
        cat = make_category(self.comp)
        make_registration(self.comp, category=cat)
        cat.is_deleted = True
        cat.save()
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        category_ids = [c["id"] for c in data["categories"]]
        self.assertIn(cat.pk, category_ids)

    def test_non_approved_competition_returns_401(self):
        comp = make_competition(
            title="Pending",
            status=Competition.Status.PENDING_APPROVAL,
            registration_enabled=True,
        )
        response = self.client.get(self.url, {"competition_token": str(comp.upload_token)})
        self.assertEqual(response.status_code, 401)


class ExportCSVViewTests(TestCase):
    def setUp(self):
        self.organizer = make_user("csvmgr", role=User.Role.ORGANIZER)
        self.comp = make_competition(submitted_by=self.organizer)
        make_registration(self.comp)

    def test_csv_returns_correct_content_type(self):
        self.client.force_login(self.organizer)
        url = reverse("registrations:export_csv", args=[self.comp.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_non_manager_gets_403(self):
        other = make_user("csvother")
        self.client.force_login(other)
        url = reverse("registrations:export_csv", args=[self.comp.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Relay registration tests
# ---------------------------------------------------------------------------


def make_relay_competition(**kwargs):
    defaults = {
        "registration_enabled": True,
        "registration_mode": "free",
        "birth_date_mode": "year",
        "status": Competition.Status.APPROVED,
        "relay_enabled": True,
        "relay_max_members": 3,
    }
    defaults.update(kwargs)
    return make_competition(**defaults)


class RelayModelTests(TestCase):
    def setUp(self):
        self.comp = make_competition()

    def test_is_relay_true_when_participant_names_set(self):
        reg = make_registration(self.comp, participant_names="Ivanov Ivan<BR>Petrov Vasya")
        self.assertTrue(reg.is_relay)

    def test_is_relay_false_when_participant_names_empty(self):
        reg = make_registration(self.comp)
        self.assertFalse(reg.is_relay)

    def test_str_individual_uses_last_first(self):
        reg = make_registration(self.comp, first_name="Ivan", last_name="Petrov")
        self.assertIn("Petrov", str(reg))
        self.assertIn("Ivan", str(reg))

    def test_str_relay_uses_participant_names(self):
        reg = make_registration(self.comp, first_name="", last_name="", participant_names="Ivanov Ivan<BR>Petrov Vasya")
        result = str(reg)
        self.assertIn("Ivanov Ivan", result)
        self.assertIn("Petrov Vasya", result)
        self.assertNotIn("<BR>", result)

    def test_relay_registration_skips_duplicate_check(self):
        # Two relay entries with empty first/last name should both save without error.
        make_registration(self.comp, first_name="", last_name="", participant_names="Team A<BR>Rider B")
        try:
            make_registration(self.comp, first_name="", last_name="", participant_names="Team C<BR>Rider D")
        except Exception as e:
            self.fail(f"Second relay registration raised {e}")


class RelayRegistrationViewTests(TestCase):
    def setUp(self):
        self.user = make_user("relayuser", gender="M", birth_date=datetime.date(1990, 1, 1))
        self.comp = make_relay_competition()
        self.cat = make_category(self.comp)
        self.url = reverse("registrations:register", args=[self.comp.pk])
        self.client.force_login(self.user)

    def test_get_shows_relay_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["relay_enabled"])
        self.assertEqual(response.context["relay_max_members"], 3)

    def test_post_relay_creates_registration_with_participant_names(self):
        response = self.client.post(
            self.url,
            {
                "participant_name": ["Ivanov Ivan", "Petrov Vasya", "Sidorov Petr"],
                "gender": "M",
                "birth_year": 1990,
                "category": self.cat.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        reg = CompetitionRegistration.objects.get(competition=self.comp)
        self.assertEqual(reg.participant_names, "Ivanov Ivan<BR>Petrov Vasya<BR>Sidorov Petr")
        self.assertEqual(reg.first_name, "")
        self.assertEqual(reg.last_name, "")
        self.assertEqual(reg.user, self.user)

    def test_post_relay_rejects_empty_names(self):
        response = self.client.post(
            self.url,
            {
                "participant_name": ["", "  "],
                "gender": "M",
                "birth_year": 1990,
                "category": self.cat.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompetitionRegistration.objects.filter(competition=self.comp).exists())

    def test_post_relay_rejects_over_max_members(self):
        response = self.client.post(
            self.url,
            {
                "participant_name": ["A", "B", "C", "D"],  # max is 3
                "gender": "M",
                "birth_year": 1990,
                "category": self.cat.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompetitionRegistration.objects.filter(competition=self.comp).exists())

    def test_post_single_relay_member_accepted(self):
        response = self.client.post(
            self.url,
            {
                "participant_name": ["Solo Rider"],
                "gender": "M",
                "birth_year": 1990,
                "category": self.cat.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        reg = CompetitionRegistration.objects.get(competition=self.comp)
        self.assertEqual(reg.participant_names, "Solo Rider")


class RelayManualAddTests(TestCase):
    def setUp(self):
        self.organizer = make_user("relayorg", role=User.Role.ORGANIZER)
        self.comp = make_relay_competition(submitted_by=self.organizer)
        self.cat = make_category(self.comp)
        self.url = reverse("registrations:manual_add", args=[self.comp.pk])
        self.client.force_login(self.organizer)

    def test_get_shows_relay_context(self):
        response = self.client.get(self.url)
        self.assertTrue(response.context["relay_enabled"])

    def test_manual_add_relay_creates_registration(self):
        response = self.client.post(
            self.url,
            {
                "participant_name": ["Kozlov Artem", "Dyakov Nikolay"],
                "gender": "M",
                "birth_year": 1992,
                "category": self.cat.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        reg = CompetitionRegistration.objects.get(competition=self.comp)
        self.assertEqual(reg.participant_names, "Kozlov Artem<BR>Dyakov Nikolay")


class RelayAPITests(TestCase):
    def setUp(self):
        self.comp = make_relay_competition()
        self.token = str(self.comp.upload_token)
        self.url = "/api/v1/participants/"

    def test_relay_participant_names_in_api(self):
        CompetitionRegistration.objects.create(
            competition=self.comp,
            first_name="",
            last_name="",
            participant_names="Ivanov Ivan<BR>Petrov Vasya",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
        )
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        self.assertEqual(data["participants"][0]["participant_names"], "Ivanov Ivan<BR>Petrov Vasya")

    def test_individual_participant_names_is_full_name(self):
        CompetitionRegistration.objects.create(
            competition=self.comp,
            first_name="Ivan",
            last_name="Petrov",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
        )
        response = self.client.get(self.url, {"competition_token": self.token})
        data = json.loads(response.content)
        self.assertEqual(data["participants"][0]["participant_names"], "Petrov Ivan")


class RelayCSVExportTests(TestCase):
    def setUp(self):
        self.organizer = make_user("relaycsv", role=User.Role.ORGANIZER)
        self.comp = make_relay_competition(submitted_by=self.organizer)
        self.url = reverse("registrations:export_csv", args=[self.comp.pk])

    def test_relay_csv_shows_semicolon_separated_names(self):
        CompetitionRegistration.objects.create(
            competition=self.comp,
            first_name="",
            last_name="",
            participant_names="Ivanov Ivan<BR>Petrov Vasya",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
        )
        self.client.force_login(self.organizer)
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("Ivanov Ivan; Petrov Vasya", content)
