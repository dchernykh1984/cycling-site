import datetime
import re
from unittest.mock import MagicMock, patch

from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.adapters import AccountAdapter, SocialAccountAdapter
from accounts.models import User
from accounts.signals import ROLE_GROUP_MAP, _sync_user_group
from accounts.wagtail_hooks import _RoleEnforcedMixin


def make_user(username="alice", role=User.Role.GUEST, **kwargs):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="Pass1234!",
        role=role,
        **kwargs,
    )
    return user


class UserModelTests(TestCase):
    def test_default_role_is_guest(self):
        user = make_user()
        self.assertEqual(user.role, User.Role.GUEST)

    def test_get_role_rank_all_roles(self):
        expected = {
            User.Role.GUEST: 0,
            User.Role.PARTICIPANT: 1,
            User.Role.ORGANIZER: 2,
            User.Role.ADMIN: 3,
            User.Role.OWNER: 4,
        }
        for role, rank in expected.items():
            user = User(role=role)
            self.assertEqual(user.get_role_rank(), rank, f"rank for {role}")

    def test_get_role_rank_unknown_role(self):
        user = User(role="nonexistent")
        self.assertEqual(user.get_role_rank(), 0)

    def test_public_display_name_uses_full_name(self):
        user = User(first_name="Anna", last_name="Smith", email="anna@example.com")
        self.assertEqual(user.public_display_name, "Anna Smith")

    def test_public_display_name_falls_back_without_exposing_email(self):
        user = User(email="secret@example.com")
        name = user.public_display_name
        self.assertNotIn("secret@example.com", name)
        self.assertTrue(name)  # a non-empty neutral label

    def test_can_assign_role_guest_cannot_assign(self):
        guest = User(role=User.Role.GUEST)
        self.assertFalse(guest.can_assign_role(User.Role.PARTICIPANT))

    def test_can_assign_role_participant_cannot_assign(self):
        participant = User(role=User.Role.PARTICIPANT)
        self.assertFalse(participant.can_assign_role(User.Role.PARTICIPANT))

    def test_can_assign_role_organizer_can_assign_organizer(self):
        organizer = User(role=User.Role.ORGANIZER)
        self.assertTrue(organizer.can_assign_role(User.Role.ORGANIZER))

    def test_can_assign_role_organizer_cannot_assign_admin(self):
        organizer = User(role=User.Role.ORGANIZER)
        self.assertFalse(organizer.can_assign_role(User.Role.ADMIN))

    def test_can_assign_role_admin_can_assign_organizer_and_admin(self):
        admin = User(role=User.Role.ADMIN)
        self.assertTrue(admin.can_assign_role(User.Role.ORGANIZER))
        self.assertTrue(admin.can_assign_role(User.Role.ADMIN))

    def test_can_assign_role_organizer_cannot_assign_participant(self):
        organizer = User(role=User.Role.ORGANIZER)
        self.assertFalse(organizer.can_assign_role(User.Role.PARTICIPANT))

    def test_can_assign_role_admin_can_assign_participant_edge_case(self):
        admin = User(role=User.Role.ADMIN)
        self.assertTrue(admin.can_assign_role(User.Role.PARTICIPANT))

    def test_can_assign_role_superuser_bypasses_role_check(self):
        superuser = User(role=User.Role.GUEST, is_superuser=True)
        for role in User.Role.values:
            self.assertTrue(superuser.can_assign_role(role), f"superuser should be able to assign {role}")

    def test_can_assign_role_unknown_target_returns_false(self):
        owner = User(role=User.Role.OWNER)
        self.assertFalse(owner.can_assign_role("nonexistent"))
        superuser = User(role=User.Role.GUEST, is_superuser=True)
        self.assertFalse(superuser.can_assign_role("nonexistent"))

    def test_can_manage_user_admin_cannot_manage_owner(self):
        admin = User(role=User.Role.ADMIN)
        owner = User(role=User.Role.OWNER)
        self.assertFalse(admin.can_manage_user(owner))

    def test_can_manage_user_admin_can_manage_organizer(self):
        admin = User(role=User.Role.ADMIN)
        organizer = User(role=User.Role.ORGANIZER)
        self.assertTrue(admin.can_manage_user(organizer))

    def test_can_manage_user_superuser_can_manage_owner(self):
        superuser = User(role=User.Role.GUEST, is_superuser=True)
        owner = User(role=User.Role.OWNER)
        self.assertTrue(superuser.can_manage_user(owner))

    def test_role_choices_contains_all_five(self):
        values = [v for v, _ in User.Role.choices]
        self.assertIn("guest", values)
        self.assertIn("participant", values)
        self.assertIn("organizer", values)
        self.assertIn("admin", values)
        self.assertIn("owner", values)


class GroupSyncTests(TestCase):
    def test_participant_role_creates_and_assigns_group(self):
        user = make_user(role=User.Role.PARTICIPANT)
        self.assertTrue(user.groups.filter(name="Participants").exists())

    def test_organizer_role_creates_and_assigns_group(self):
        user = make_user(role=User.Role.ORGANIZER)
        self.assertTrue(user.groups.filter(name="Organizers").exists())

    def test_guest_role_has_no_managed_group(self):
        user = make_user(role=User.Role.GUEST)
        managed = set(ROLE_GROUP_MAP.values())
        self.assertFalse(user.groups.filter(name__in=managed).exists())

    def test_role_change_swaps_group(self):
        user = make_user(role=User.Role.PARTICIPANT)
        self.assertTrue(user.groups.filter(name="Participants").exists())

        user.role = User.Role.ORGANIZER
        user.save()

        self.assertFalse(user.groups.filter(name="Participants").exists())
        self.assertTrue(user.groups.filter(name="Organizers").exists())

    def test_role_change_to_guest_removes_group(self):
        user = make_user(role=User.Role.PARTICIPANT)
        user.role = User.Role.GUEST
        user.save()
        managed = set(ROLE_GROUP_MAP.values())
        self.assertFalse(user.groups.filter(name__in=managed).exists())

    def test_sync_is_idempotent(self):
        user = make_user(role=User.Role.PARTICIPANT)
        _sync_user_group(user)
        _sync_user_group(user)
        self.assertEqual(user.groups.filter(name="Participants").count(), 1)

    def test_sync_removes_stale_group_when_group_deleted(self):
        user = make_user(role=User.Role.PARTICIPANT)
        Group.objects.filter(name="Participants").delete()
        user.role = User.Role.GUEST
        user.save()
        managed = set(ROLE_GROUP_MAP.values())
        self.assertFalse(user.groups.filter(name__in=managed).exists())

    def test_sync_cleans_stale_groups_when_target_already_present(self):
        user = make_user(role=User.Role.PARTICIPANT)
        admins_group, _ = Group.objects.get_or_create(name="Admins")
        user.groups.add(admins_group)
        _sync_user_group(user)
        self.assertTrue(user.groups.filter(name="Participants").exists())
        self.assertFalse(user.groups.filter(name="Admins").exists())


class EmailConfirmedSignalTests(TestCase):
    def test_email_confirmed_upgrades_guest_to_participant(self):
        user = make_user(role=User.Role.GUEST)
        ea = EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)

        request = RequestFactory().get("/")
        email_confirmed.send(sender=EmailAddress, request=request, email_address=ea)

        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.PARTICIPANT)

    def test_email_confirmed_does_not_downgrade_existing_role(self):
        user = make_user(role=User.Role.ORGANIZER)
        ea = EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)

        request = RequestFactory().get("/")
        email_confirmed.send(sender=EmailAddress, request=request, email_address=ea)

        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.ORGANIZER)


class AccountAdapterTests(TestCase):
    def test_save_user_sets_guest_role(self):
        adapter = AccountAdapter()
        request = RequestFactory().get("/")

        user = User()
        form = MagicMock()

        with patch("allauth.account.adapter.DefaultAccountAdapter.save_user", return_value=user):
            result = adapter.save_user(request, user, form, commit=False)

        self.assertEqual(result.role, User.Role.GUEST)

    def test_save_user_with_commit_saves_to_db(self):
        adapter = AccountAdapter()
        request = RequestFactory().get("/")
        form = MagicMock()

        user = User(username="adaptertest", email="adaptertest@example.com")
        user.set_password("Pass1234!")

        with patch("allauth.account.adapter.DefaultAccountAdapter.save_user", return_value=user):
            result = adapter.save_user(request, user, form, commit=True)

        self.assertEqual(result.role, User.Role.GUEST)
        self.assertTrue(User.objects.filter(username="adaptertest").exists())


class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = make_user(username="viewer", role=User.Role.PARTICIPANT)

    def test_profile_redirects_anonymous(self):
        response = self.client.get(reverse("account_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_profile_accessible_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_profile"))
        self.assertEqual(response.status_code, 200)

    def test_profile_contains_user_email(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_profile"))
        self.assertContains(response, self.user.email)

    def test_profile_shows_unverified_warning_without_confirmed_email(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_profile"))
        self.assertContains(response, "alert-warning")

    def test_profile_hides_unverified_warning_when_email_confirmed(self):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_profile"))
        self.assertNotContains(response, "alert-warning")


class ProfileRegistrationListTests(TestCase):
    """Profile page 'My registrations' section shows only the logged-in user's registrations
    across all competition types and hides other users' registrations."""

    def setUp(self):
        import datetime

        from calendar_app.models import Competition
        from registrations.models import CompetitionRegistration

        self.Competition = Competition
        self.CompetitionRegistration = CompetitionRegistration

        self.user = make_user("reg_user", role=User.Role.PARTICIPANT, gender="M", birth_date=datetime.date(1990, 1, 1))
        self.other = make_user("other_user", role=User.Role.PARTICIPANT)
        self.url = reverse("account_profile")

    def _make_comp(self, **kwargs):
        import datetime

        defaults = {
            "title_ru": "Race",
            "date_start": datetime.date(2026, 9, 1),
            "status": self.Competition.Status.APPROVED,
            "registration_enabled": True,
            "registration_mode": self.Competition.RegistrationMode.FREE,
            "birth_date_mode": "year",
        }
        defaults.update(kwargs)
        return self.Competition.objects.create(**defaults)

    _UNSET = object()

    def _make_reg(self, competition, user=_UNSET, **kwargs):
        import datetime

        defaults = {
            "competition": competition,
            "user": self.user if user is self._UNSET else user,
            "first_name": "Denis",
            "last_name": "Test",
            "birth_date": datetime.date(1990, 1, 1),
            "gender": "M",
        }
        defaults.update(kwargs)
        return self.CompetitionRegistration.objects.create(**defaults)

    def _registrations_in_response(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return list(response.context["registrations"])

    def test_self_only_registration_appears_in_profile(self):
        comp = self._make_comp(registration_mode=self.Competition.RegistrationMode.SELF_ONLY)
        reg = self._make_reg(comp)
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_free_mode_registration_appears_in_profile(self):
        comp = self._make_comp(registration_mode=self.Competition.RegistrationMode.FREE)
        reg = self._make_reg(comp)
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_relay_registration_appears_in_profile(self):
        comp = self._make_comp(
            registration_mode=self.Competition.RegistrationMode.FREE,
            relay_enabled=True,
            relay_max_members=4,
        )
        reg = self._make_reg(comp, first_name="", last_name="", participant_names="Ivan<BR>Vasya")
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_registration_with_approval_required_appears_in_profile(self):
        comp = self._make_comp(require_approval=True)
        reg = self._make_reg(comp, is_approved=False)
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_registration_with_payment_required_appears_in_profile(self):
        comp = self._make_comp(require_payment=True)
        reg = self._make_reg(comp, is_paid=False)
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_approved_registration_appears_in_profile(self):
        comp = self._make_comp(require_approval=True)
        reg = self._make_reg(comp, is_approved=True)
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_rejected_registration_appears_in_profile(self):
        comp = self._make_comp(require_approval=True)
        reg = self._make_reg(comp, is_rejected=True, rejection_note="Too slow")
        regs = self._registrations_in_response()
        self.assertIn(reg, regs)

    def test_other_users_registration_not_shown(self):
        comp = self._make_comp()
        own_reg = self._make_reg(comp, user=self.user)
        other_reg = self._make_reg(comp, user=self.other, first_name="Other")
        regs = self._registrations_in_response()
        self.assertIn(own_reg, regs)
        self.assertNotIn(other_reg, regs)

    def test_registration_with_user_none_not_shown(self):
        comp = self._make_comp()
        self._make_reg(comp, user=None)
        regs = self._registrations_in_response()
        self.assertEqual(len(regs), 0)

    def test_profile_shows_no_registrations_when_none(self):
        regs = self._registrations_in_response()
        self.assertEqual(len(regs), 0)

    def _response(self):
        self.client.force_login(self.user)
        return self.client.get(self.url)

    def test_no_approval_required_shows_approved_badge(self):
        comp = self._make_comp(require_approval=False)
        self._make_reg(comp, is_approved=True)
        self.assertContains(self._response(), "bg-success")
        self.assertNotContains(self._response(), "bg-warning")

    def test_approval_required_pending_shows_pending_badge(self):
        comp = self._make_comp(require_approval=True)
        self._make_reg(comp, is_approved=False)
        self.assertContains(self._response(), "bg-warning")

    def test_approval_required_approved_shows_success_badge(self):
        comp = self._make_comp(require_approval=True)
        self._make_reg(comp, is_approved=True)
        self.assertContains(self._response(), "bg-success")

    @override_settings(LANGUAGE_CODE="en")
    def test_payment_required_unpaid_shows_not_paid_badge(self):
        comp = self._make_comp(require_approval=False, require_payment=True)
        self._make_reg(comp, is_approved=True, is_paid=False)
        self.assertContains(self._response(), "Not paid")

    @override_settings(LANGUAGE_CODE="en")
    def test_payment_required_paid_shows_paid_badge(self):
        comp = self._make_comp(require_approval=False, require_payment=True)
        self._make_reg(comp, is_approved=True, is_paid=True)
        self.assertContains(self._response(), "Paid")

    def test_no_payment_required_no_payment_badge(self):
        comp = self._make_comp(require_payment=False)
        self._make_reg(comp, is_approved=True, is_paid=True)
        self.assertNotContains(self._response(), "Not paid")


class RegistrationFlowTests(TestCase):
    def test_signup_creates_guest_user(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "newuser@example.com",
                "password1": "SuperPass123!",
                "password2": "SuperPass123!",
            },
        )
        self.assertIn(response.status_code, [200, 302])
        user = User.objects.get(email="newuser@example.com")
        self.assertEqual(user.role, User.Role.GUEST)

    def test_signup_with_existing_email_does_not_reveal_account(self):
        # Enumeration prevention (review #4): signing up with an existing email must not
        # error that the email is taken, nor create a duplicate account.
        User.objects.create_user(username="exists@example.com", email="exists@example.com", password="SuperPass123!")
        response = self.client.post(
            reverse("account_signup"),
            {"email": "exists@example.com", "password1": "SuperPass123!", "password2": "SuperPass123!"},
        )
        self.assertIn(response.status_code, [200, 302])
        self.assertNotIn(b"already registered", response.content)
        self.assertEqual(User.objects.filter(email="exists@example.com").count(), 1)

    def test_email_confirmation_flow(self):
        from django.core import mail

        self.client.post(
            reverse("account_signup"),
            {
                "email": "confirm@example.com",
                "password1": "SuperPass123!",
                "password2": "SuperPass123!",
            },
        )
        user = User.objects.get(email="confirm@example.com")
        self.assertEqual(user.role, User.Role.GUEST)

        self.assertGreater(len(mail.outbox), 0, "Confirmation email was not sent")
        email_body = mail.outbox[0].body
        match = re.search(r"http[s]?://\S+/accounts/confirm-email/\S+/", email_body)
        self.assertIsNotNone(match, "Confirmation URL not found in email body")
        confirm_url = match.group(0).replace("http://testserver", "")  # type: ignore[union-attr]
        # allauth 65.x HMAC flow: GET shows form, POST actually confirms
        self.client.post(confirm_url)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.PARTICIPANT)


class SocialAccountAdapterTests(TestCase):
    def _make_sociallogin(self, verified=True, has_email=True):
        sociallogin = MagicMock()
        if has_email:
            ea = MagicMock()
            ea.verified = verified
            sociallogin.email_addresses = [ea]
        else:
            sociallogin.email_addresses = []
        return sociallogin

    def _call_adapter(self, user, sociallogin):
        adapter = SocialAccountAdapter()
        request = RequestFactory().get("/")
        with patch(
            "allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user",
            return_value=user,
        ):
            return adapter.save_user(request, sociallogin, form=None)

    def test_verified_social_email_upgrades_guest_to_participant(self):
        user = make_user(username="social_verified", role=User.Role.GUEST)
        self._call_adapter(user, self._make_sociallogin(verified=True))
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.PARTICIPANT)

    def test_unverified_social_email_stays_guest(self):
        user = make_user(username="social_unverified", role=User.Role.GUEST)
        self._call_adapter(user, self._make_sociallogin(verified=False))
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.GUEST)

    def test_no_email_stays_guest(self):
        user = make_user(username="telegram_user", role=User.Role.GUEST)
        self._call_adapter(user, self._make_sociallogin(has_email=False))
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.GUEST)

    def test_existing_higher_role_not_overwritten(self):
        user = make_user(username="organizer_social", role=User.Role.ORGANIZER)
        self._call_adapter(user, self._make_sociallogin(verified=True))
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.ORGANIZER)

    def _call_pre_social_login(self, user, verified=True, has_email=True):
        adapter = SocialAccountAdapter()
        request = RequestFactory().get("/")
        sociallogin = MagicMock()
        sociallogin.is_existing = True
        sociallogin.user = user
        if has_email:
            ea = MagicMock()
            ea.verified = verified
            sociallogin.email_addresses = [ea]
        else:
            sociallogin.email_addresses = []
        adapter.pre_social_login(request, sociallogin)

    def test_pre_social_login_upgrades_existing_guest_with_verified_email(self):
        user = make_user(username="pre_verified", role=User.Role.GUEST)
        self._call_pre_social_login(user, verified=True)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.PARTICIPANT)

    def test_pre_social_login_unverified_email_stays_guest(self):
        user = make_user(username="pre_unverified", role=User.Role.GUEST)
        self._call_pre_social_login(user, verified=False)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.GUEST)

    def test_pre_social_login_no_email_stays_guest(self):
        user = make_user(username="pre_noemail", role=User.Role.GUEST)
        self._call_pre_social_login(user, has_email=False)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.GUEST)


class RoleEnforcedMixinTests(TestCase):
    """Unit tests for _RoleEnforcedMixin without going through the full Wagtail HTTP stack."""

    def _make_view(self, editor_role, target_user=None):
        """Return a view instance with the mixin and a trivial super().form_valid."""
        editor = User(role=editor_role)
        editor.ROLE_HIERARCHY = User.ROLE_HIERARCHY

        class BaseView:
            def form_valid(self, form):
                return "valid"

            def form_invalid(self, form):
                return "invalid"

        class TestView(_RoleEnforcedMixin, BaseView):
            pass

        request = RequestFactory().post("/")
        request.user = editor
        view = TestView()
        view.request = request
        if target_user is not None:
            view.object = target_user
        return view

    def test_blocks_role_editor_cannot_assign(self):
        view = self._make_view(User.Role.ADMIN)
        form = MagicMock()
        form.cleaned_data = {"role": User.Role.OWNER}
        result = view.form_valid(form)
        self.assertEqual(result, "invalid")
        form.add_error.assert_called_once()

    def test_allows_role_editor_can_assign(self):
        # Only a superuser (which OWNER becomes on save) can assign the OWNER role.
        # Simulate an actual saved OWNER by setting is_superuser=True explicitly.
        view = self._make_view(User.Role.OWNER)
        view.request.user.is_superuser = True
        form = MagicMock()
        form.cleaned_data = {"role": User.Role.OWNER}
        result = view.form_valid(form)
        self.assertEqual(result, "valid")

    def test_no_role_in_form_passes_through(self):
        view = self._make_view(User.Role.ADMIN)
        form = MagicMock()
        form.cleaned_data = {}
        result = view.form_valid(form)
        self.assertEqual(result, "valid")

    def test_blocks_when_editor_cannot_manage_target(self):
        owner = User(role=User.Role.OWNER)
        view = self._make_view(User.Role.ADMIN, target_user=owner)
        form = MagicMock()
        form.cleaned_data = {"role": User.Role.ADMIN}
        result = view.form_valid(form)
        self.assertEqual(result, "invalid")
        form.add_error.assert_called_once()


class WagtailUserViewSetTests(TestCase):
    def test_copy_view_disabled(self):
        from accounts.wagtail_hooks import UserViewSet

        self.assertFalse(UserViewSet.copy_view_enabled)


class DjangoAdminRoleEnforcementTests(TestCase):
    def _make_staff_user(self, username, role):
        """Non-superuser staff user with all User model permissions."""
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        user = make_user(username=username, role=role)
        user.is_staff = True
        user.save()
        ct = ContentType.objects.get_for_model(User)
        user.user_permissions.set(Permission.objects.filter(content_type=ct))
        return user

    def _change_url(self, target):
        return reverse("admin:accounts_user_change", args=[target.pk])

    def _post_role_change(self, target, new_role):
        return self.client.post(
            self._change_url(target),
            {
                "username": target.username,
                "email": target.email,
                "role": new_role,
                "is_active": "on",
                "date_joined_0": "2024-01-01",
                "date_joined_1": "00:00:00",
                "_save": "Save",
            },
        )

    def test_admin_cannot_assign_owner_via_django_admin(self):
        admin = self._make_staff_user("admin_da", User.Role.ADMIN)
        self.client.force_login(admin)
        target = make_user(username="target_da", role=User.Role.PARTICIPANT)
        self._post_role_change(target, User.Role.OWNER)
        target.refresh_from_db()
        self.assertNotEqual(target.role, User.Role.OWNER)

    def test_owner_can_assign_owner_via_django_admin(self):
        owner = self._make_staff_user("owner_da", User.Role.OWNER)
        self.client.force_login(owner)
        target = make_user(username="target_da2", role=User.Role.ADMIN)
        self._post_role_change(target, User.Role.OWNER)
        target.refresh_from_db()
        self.assertEqual(target.role, User.Role.OWNER)

    def test_superuser_with_guest_role_can_assign_any_role(self):
        """Bootstrap: createsuperuser (is_superuser=True, role=guest) bypasses role checks."""
        superuser = make_user(username="bootstrap_su", role=User.Role.GUEST)
        superuser.is_superuser = True
        superuser.save()
        self.assertTrue(superuser.can_assign_role(User.Role.OWNER))
        self.assertTrue(superuser.can_assign_role(User.Role.ADMIN))

    def test_admin_cannot_demote_owner_via_django_admin(self):
        admin = self._make_staff_user("admin_dem", User.Role.ADMIN)
        self.client.force_login(admin)
        target = make_user(username="target_dem", role=User.Role.OWNER)
        self._post_role_change(target, User.Role.ADMIN)
        target.refresh_from_db()
        self.assertEqual(target.role, User.Role.OWNER)

    def test_admin_cannot_escalate_is_superuser_via_django_admin(self):
        admin = self._make_staff_user("admin_esc", User.Role.ADMIN)
        self.client.force_login(admin)
        target = make_user(username="target_esc", role=User.Role.PARTICIPANT)
        self.client.post(
            self._change_url(target),
            {
                "username": target.username,
                "email": target.email,
                "role": target.role,
                "is_active": "on",
                "is_superuser": "on",
                "date_joined_0": "2024-01-01",
                "date_joined_1": "00:00:00",
                "_save": "Save",
            },
        )
        target.refresh_from_db()
        self.assertFalse(target.is_superuser)


class ResendEmailConfirmationTests(TestCase):
    def setUp(self):
        self.user = make_user(username="resender", role=User.Role.GUEST)
        self.url = reverse("account_resend_confirmation")

    def test_redirects_anonymous(self):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_sends_confirmation_and_sets_cooldown(self):
        self.client.force_login(self.user)
        with patch.object(EmailAddress, "send_confirmation") as mock_send:
            resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        mock_send.assert_called_once()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_mail_action_at)

    def test_cooldown_prevents_immediate_resend(self):
        self.client.force_login(self.user)
        with patch.object(EmailAddress, "send_confirmation"):
            self.client.post(self.url)
        with patch.object(EmailAddress, "send_confirmation") as mock_send:
            resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        mock_send.assert_not_called()

    def test_already_verified_skips_send(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        self.client.force_login(self.user)
        with patch.object(EmailAddress, "send_confirmation") as mock_send:
            resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        mock_send.assert_not_called()

    def test_profile_shows_resend_button_when_unverified(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("account_profile"))
        self.assertContains(resp, "/accounts/resend-confirmation/")

    def test_profile_button_disabled_during_cooldown(self):
        self.client.force_login(self.user)
        with patch.object(EmailAddress, "send_confirmation"):
            self.client.post(self.url)
        resp = self.client.get(reverse("account_profile"))
        self.assertContains(resp, "disabled")

    def test_concurrent_resends_send_only_one_email(self):
        # A second resend from the same guest arriving while the first is still inside
        # send_confirmation() must be throttled: the slot is reserved before sending, so a
        # check-then-send-then-save TOCTOU race cannot fire two confirmation emails.
        from django.test import Client

        self.client.force_login(self.user)
        concurrent = Client()
        concurrent.force_login(self.user)
        original = EmailAddress.send_confirmation
        state = {"reentered": False}

        def reentrant_send(email_address, *args, **kwargs):
            if not state["reentered"]:
                state["reentered"] = True
                concurrent.post(self.url)  # concurrent resend lands mid-send
            return original(email_address, *args, **kwargs)

        with patch.object(EmailAddress, "send_confirmation", autospec=True, side_effect=reentrant_send):
            resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertTrue(state["reentered"])  # the concurrent resend really ran mid-send
        self.assertEqual(len(mail.outbox), 1)  # only one confirmation email went out

    def test_send_failure_releases_resend_slot(self):
        self.client.force_login(self.user)
        with (
            patch.object(EmailAddress, "send_confirmation", side_effect=Exception("smtp down")),
            self.assertLogs("accounts.views", level="ERROR") as cm,
        ):
            resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_mail_action_at)  # slot released so the guest can retry
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(any("Failed to resend confirmation email" in line for line in cm.output))


class _DjangoAdminRoleEnforcementExtraTests(TestCase):
    def _make_staff_user(self, username, role):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        user = make_user(username=username, role=role)
        user.is_staff = True
        user.save()
        ct = ContentType.objects.get_for_model(User)
        user.user_permissions.set(Permission.objects.filter(content_type=ct))
        return user

    def _change_url(self, target):
        return reverse("admin:accounts_user_change", args=[target.pk])

    def test_owner_can_set_is_staff_via_django_admin(self):
        owner = self._make_staff_user("owner_staff", User.Role.OWNER)
        self.client.force_login(owner)
        target = make_user(username="target_staff", role=User.Role.ADMIN)
        self.client.post(
            self._change_url(target),
            {
                "username": target.username,
                "email": target.email,
                "role": target.role,
                "is_active": "on",
                "is_staff": "on",
                "date_joined_0": "2024-01-01",
                "date_joined_1": "00:00:00",
                "_save": "Save",
            },
        )
        target.refresh_from_db()
        self.assertTrue(target.is_staff)


class InitialSuperuserMigrationTests(TestCase):
    @staticmethod
    def _get_fn():
        import importlib

        module = importlib.import_module("accounts.migrations.0002_initial_superuser")
        return module.create_initial_superuser

    def test_creates_superuser_when_env_vars_set(self):
        fn = self._get_fn()
        env = {
            "INITIAL_SUPERUSER_USERNAME": "deploy_admin",
            "INITIAL_SUPERUSER_PASSWORD": "StrongPass999!",
        }
        with patch.dict("os.environ", env, clear=False):
            fn(apps=None, schema_editor=None)

        user = User.objects.get(username="deploy_admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_skips_when_env_vars_missing(self):
        fn = self._get_fn()
        with patch.dict("os.environ", {}, clear=True):
            fn(apps=None, schema_editor=None)
        self.assertFalse(User.objects.filter(username="deploy_admin").exists())

    def test_idempotent_when_user_already_exists(self):
        fn = self._get_fn()
        User.objects.create_superuser(username="existing_su", email="su@localhost", password="x")
        env = {
            "INITIAL_SUPERUSER_USERNAME": "existing_su",
            "INITIAL_SUPERUSER_PASSWORD": "AnotherPass!",
        }
        with patch.dict("os.environ", env, clear=False):
            fn(apps=None, schema_editor=None)
        self.assertEqual(User.objects.filter(username="existing_su").count(), 1)


class MigrateRepairCommandTests(TestCase):
    def test_repair_is_noop_when_accounts_migration_already_applied(self):
        from accounts.management.commands.migrate import _repair_accounts_initial_if_needed

        # Test DB has all migrations applied - function should return silently.
        _repair_accounts_initial_if_needed()

    def test_repair_handles_recorder_exception_gracefully(self):
        from accounts.management.commands.migrate import _repair_accounts_initial_if_needed

        with patch("accounts.management.commands.migrate.MigrationRecorder") as mock_cls:
            mock_cls.return_value.applied_migrations.side_effect = Exception("DB unavailable")
            _repair_accounts_initial_if_needed()


class ProfileEditViewTests(TestCase):
    def setUp(self):
        self.user = make_user(username="editme", role=User.Role.PARTICIPANT)

    def test_get_shows_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_profile_edit"))
        self.assertEqual(response.status_code, 200)

    def test_redirects_anonymous(self):
        response = self.client.get(reverse("account_profile_edit"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_post_updates_profile(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("account_profile_edit"),
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "gender": "F",
                "birth_date": "1995-03-10",
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Alice")
        self.assertEqual(self.user.gender, "F")
        self.assertEqual(self.user.birth_date, datetime.date(1995, 3, 10))

    def test_birth_date_prefilled_as_iso_under_ru_locale(self):
        # Regression: ru-locale L10N rendered the date in a localized form, which an
        # <input type=date> rejects, leaving it blank. It must be pre-filled as ISO YYYY-MM-DD.
        import re

        self.user.birth_date = datetime.date(1990, 6, 21)
        self.user.save()
        self.client.force_login(self.user)
        resp = self.client.get(reverse("account_profile_edit"), HTTP_ACCEPT_LANGUAGE="ru")
        m = re.search(r'name="birth_date"[^>]*value="([^"]*)"', resp.content.decode())
        self.assertEqual(m.group(1), "1990-06-21")

    def test_post_redirects_to_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_profile_edit"),
            {
                "first_name": "Bob",
                "last_name": "Jones",
            },
        )
        self.assertRedirects(response, reverse("account_profile"))


class UserGenderBirthDateTests(TestCase):
    def test_gender_and_birth_date_defaults_to_empty(self):
        user = make_user(username="newuser")
        self.assertEqual(user.gender, "")
        self.assertIsNone(user.birth_date)

    def test_gender_and_birth_date_can_be_saved(self):
        user = make_user(username="savegender")
        user.gender = "M"
        user.birth_date = datetime.date(1990, 6, 15)
        user.save(update_fields=["gender", "birth_date"])
        user.refresh_from_db()
        self.assertEqual(user.gender, "M")
        self.assertEqual(user.birth_date, datetime.date(1990, 6, 15))


class ThemeFieldTests(TestCase):
    def test_default_theme_is_light(self):
        user = make_user(username="theme_user")
        self.assertEqual(user.theme, "light")

    def test_theme_can_be_set_to_dark(self):
        user = make_user(username="dark_user")
        user.theme = "dark"
        user.save(update_fields=["theme"])
        user.refresh_from_db()
        self.assertEqual(user.theme, "dark")


class ThemeUpdateViewTests(TestCase):
    def setUp(self):
        self.user = make_user(username="theme_view_user")
        self.client.login(username="theme_view_user@example.com", password="Pass1234!")

    def test_update_theme_to_dark(self):
        import json

        response = self.client.post(
            reverse("account_theme"),
            data=json.dumps({"theme": "dark"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "dark")

    def test_update_theme_rejects_invalid_value(self):
        import json

        response = self.client.post(
            reverse("account_theme"),
            data=json.dumps({"theme": "rainbow"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_update_theme_requires_auth(self):
        import json

        self.client.logout()
        response = self.client.post(
            reverse("account_theme"),
            data=json.dumps({"theme": "dark"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, [302, 403])


class ApiTokenRegenerateViewTests(TestCase):
    def setUp(self):
        self.url = reverse("account_api_token_regenerate")

    def test_guest_cannot_generate_token(self):
        guest = make_user(username="token_guest", role=User.Role.GUEST)
        self.client.force_login(guest)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_participant_can_generate_token(self):
        participant = make_user(username="token_part", role=User.Role.PARTICIPANT)
        self.client.force_login(participant)
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        participant.refresh_from_db()
        self.assertIsNotNone(participant.api_token)

    def test_organizer_can_generate_token(self):
        organizer = make_user(username="token_org", role=User.Role.ORGANIZER)
        self.client.force_login(organizer)
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("account_profile"))
        organizer.refresh_from_db()
        self.assertIsNotNone(organizer.api_token)

    def test_profile_shows_api_section_for_participant(self):
        participant = make_user(username="api_part_profile", role=User.Role.PARTICIPANT)
        self.client.force_login(participant)
        resp = self.client.get(reverse("account_profile"))
        self.assertContains(resp, "api-token/regenerate")

    def test_profile_hides_api_section_for_guest(self):
        guest = make_user(username="api_guest_profile", role=User.Role.GUEST)
        self.client.force_login(guest)
        resp = self.client.get(reverse("account_profile"))
        self.assertNotContains(resp, "api-token/regenerate")

    def test_regenerate_invalidates_old_token(self):
        participant = make_user(username="token_rotate", role=User.Role.PARTICIPANT)
        self.client.force_login(participant)

        self.client.post(self.url)
        participant.refresh_from_db()
        old_token = participant.api_token
        self.assertIsNotNone(old_token)
        self.assertEqual(
            self.client.get("/api/v1/competitions/", HTTP_AUTHORIZATION=f"Bearer {old_token}").status_code,
            200,
        )

        self.client.post(self.url)
        participant.refresh_from_db()
        new_token = participant.api_token
        self.assertNotEqual(new_token, old_token)

        # The regenerated token replaces the field, so the old token matches no user.
        self.assertEqual(
            self.client.get("/api/v1/competitions/", HTTP_AUTHORIZATION=f"Bearer {old_token}").status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/v1/competitions/", HTTP_AUTHORIZATION=f"Bearer {new_token}").status_code,
            200,
        )


class ContactOwnersViewTests(TestCase):
    """Registered users (participant+) can email the site owners (issue #122)."""

    def setUp(self):
        self.url = reverse("account_contact_owners")

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_guest_cannot_access(self):
        guest = make_user(username="contact_guest", role=User.Role.GUEST)
        self.client.force_login(guest)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"subject": "x", "message": "y"}).status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_participant_can_open_form(self):
        self.client.force_login(make_user(username="contact_part", role=User.Role.PARTICIPANT))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="subject"')
        self.assertContains(resp, 'name="message"')

    def test_post_sends_email_to_owner_mailbox(self):
        self.client.force_login(make_user(username="contact_sender", role=User.Role.PARTICIPANT))
        resp = self.client.post(self.url, {"subject": "Need help", "message": "Reach me at @mytg; my problem is X."})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [settings.DEFAULT_FROM_EMAIL])
        self.assertEqual(msg.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn("Need help", msg.subject)
        self.assertIn("contact_sender@example.com", msg.body)
        self.assertIn("contact_sender", msg.body)
        self.assertIn("Reach me at @mytg", msg.body)

    def test_organizer_can_send(self):
        self.client.force_login(make_user(username="contact_org", role=User.Role.ORGANIZER))
        resp = self.client.post(self.url, {"subject": "Q", "message": "body"})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)

    def test_empty_message_shows_error_and_sends_nothing(self):
        self.client.force_login(make_user(username="contact_empty", role=User.Role.PARTICIPANT))
        resp = self.client.post(self.url, {"subject": "Hi", "message": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("message", resp.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_profile_shows_contact_button_for_participant(self):
        self.client.force_login(make_user(username="contact_btn", role=User.Role.PARTICIPANT))
        resp = self.client.get(reverse("account_profile"))
        self.assertContains(resp, reverse("account_contact_owners"))

    def test_contact_button_disabled_with_countdown_during_cooldown(self):
        user = make_user(username="contact_cd_btn", role=User.Role.PARTICIPANT)
        user.last_mail_action_at = timezone.now()
        user.save(update_fields=["last_mail_action_at"])
        self.client.force_login(user)
        resp = self.client.get(reverse("account_profile"))
        self.assertGreater(resp.context["contact_cooldown_seconds"], 0)
        self.assertContains(resp, "btn btn-sm btn-outline-primary disabled")

    def test_contact_button_enabled_without_cooldown(self):
        self.client.force_login(make_user(username="contact_nocd_btn", role=User.Role.PARTICIPANT))
        resp = self.client.get(reverse("account_profile"))
        self.assertEqual(resp.context["contact_cooldown_seconds"], 0)
        self.assertNotContains(resp, "btn btn-sm btn-outline-primary disabled")

    def test_profile_hides_contact_button_for_guest(self):
        self.client.force_login(make_user(username="contact_nobtn", role=User.Role.GUEST))
        resp = self.client.get(reverse("account_profile"))
        self.assertNotContains(resp, reverse("account_contact_owners"))

    def test_second_message_is_rate_limited(self):
        self.client.force_login(make_user(username="contact_rl", role=User.Role.PARTICIPANT))
        r1 = self.client.post(self.url, {"subject": "a", "message": "b"})
        self.assertRedirects(r1, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)
        r2 = self.client.post(self.url, {"subject": "c", "message": "d"})
        self.assertEqual(r2.status_code, 200)  # blocked, re-rendered (not sent)
        self.assertEqual(len(mail.outbox), 1)

    def test_can_send_again_after_cooldown(self):
        user = make_user(username="contact_cd", role=User.Role.PARTICIPANT)
        self.client.force_login(user)
        self.assertRedirects(self.client.post(self.url, {"subject": "a", "message": "b"}), reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)
        User.objects.filter(pk=user.pk).update(last_mail_action_at=timezone.now() - datetime.timedelta(seconds=601))
        self.assertRedirects(self.client.post(self.url, {"subject": "c", "message": "d"}), reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 2)

    def test_overlong_message_is_rejected(self):
        self.client.force_login(make_user(username="contact_long", role=User.Role.PARTICIPANT))
        resp = self.client.post(self.url, {"subject": "S", "message": "x" * 5001})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("message", resp.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_long_but_allowed_message_is_sent(self):
        self.client.force_login(make_user(username="contact_ok_long", role=User.Role.PARTICIPANT))
        resp = self.client.post(self.url, {"subject": "S", "message": "y" * 5000})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)

    def test_email_failure_is_logged_and_does_not_500(self):
        from unittest.mock import patch

        self.client.force_login(make_user(username="contact_fail", role=User.Role.PARTICIPANT))
        with (
            patch("accounts.views.send_mail", side_effect=Exception("smtp down")),
            self.assertLogs("accounts.views", level="ERROR") as cm,
        ):
            resp = self.client.post(self.url, {"subject": "S", "message": "M"})
        self.assertEqual(resp.status_code, 200)  # re-rendered, not a 500 or redirect
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(any("Failed to send contact-owners email" in line for line in cm.output))

    def test_subject_newlines_are_sanitized(self):
        self.client.force_login(make_user(username="contact_nl", role=User.Role.PARTICIPANT))
        resp = self.client.post(self.url, {"subject": "Line1\nLine2\rLine3", "message": "M"})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("\n", mail.outbox[0].subject)
        self.assertNotIn("\r", mail.outbox[0].subject)
        self.assertIn("Line1 Line2 Line3", mail.outbox[0].subject)

    def test_owner_email_is_fixed_english_regardless_of_locale(self):
        # The owner notification is internal and must not depend on the sender's UI language.
        self.client.force_login(make_user(username="contact_en", role=User.Role.PARTICIPANT))
        resp = self.client.post(self.url, {"subject": "Hi", "message": "M"}, headers={"accept-language": "ru"})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("New message from a registered site user", mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].subject.startswith("Site contact:"))

    def test_labels_are_localized(self):
        # The page must render the Russian translation (pulled from the catalog, not the
        # English source) - confirms the .po/.mo translations are wired up.
        from django.utils import translation

        with translation.override("ru"):
            expected = translation.gettext("Contact site owners")
        self.assertNotEqual(expected, "Contact site owners")  # a real translation exists
        self.client.force_login(make_user(username="contact_loc", role=User.Role.PARTICIPANT))
        resp = self.client.get(self.url, headers={"accept-language": "ru"})
        self.assertContains(resp, expected)

    def test_concurrent_posts_reserve_slot_and_send_one_email(self):
        # The slot must be reserved (timestamp flipped) *before* the email is sent, so a
        # second request from the same user arriving mid-send is throttled. A
        # check-then-send-then-save flow (TOCTOU) would let both pass the stale check and
        # fire two emails. We simulate the concurrent request from inside send_mail().
        from unittest.mock import patch

        from django.test import Client

        from accounts import views as accounts_views

        user = make_user(username="contact_race", role=User.Role.PARTICIPANT)
        self.client.force_login(user)
        concurrent = Client()
        concurrent.force_login(user)

        original_send_mail = accounts_views.send_mail
        state = {"reentered": False}

        def reentrant_send_mail(*args, **kwargs):
            if not state["reentered"]:
                state["reentered"] = True
                # A concurrent POST from the same user lands while we are still "sending".
                concurrent.post(self.url, {"subject": "race2", "message": "m2"})
            return original_send_mail(*args, **kwargs)

        with patch("accounts.views.send_mail", side_effect=reentrant_send_mail):
            resp = self.client.post(self.url, {"subject": "race1", "message": "m1"})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertTrue(state["reentered"])  # the concurrent request really ran mid-send
        self.assertEqual(len(mail.outbox), 1)  # only the first send went out

    def test_send_failure_releases_slot_for_retry(self):
        from unittest.mock import patch

        user = make_user(username="contact_release", role=User.Role.PARTICIPANT)
        self.client.force_login(user)
        with patch("accounts.views.send_mail", side_effect=Exception("smtp down")):
            self.client.post(self.url, {"subject": "S", "message": "M"})
        user.refresh_from_db()
        # The reserved slot is rolled back so a transient failure does not lock the user out.
        self.assertIsNone(user.last_mail_action_at)
        resp = self.client.post(self.url, {"subject": "S2", "message": "M2"})
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)


class OptionalEmailVerificationTests(TestCase):
    """With ACCOUNT_EMAIL_VERIFICATION='optional' an unverified user can log in but gets a
    minimal cabinet (data + resend) until they confirm and become participant+."""

    def test_signup_logs_in_unverified_user(self):
        self.client.post(
            reverse("account_signup"),
            {"email": "opt_signup@example.com", "password1": "SuperPass123!", "password2": "SuperPass123!"},
        )
        # optional verification logs the user in immediately (mandatory would not)
        self.assertEqual(self.client.get(reverse("account_profile")).status_code, 200)

    def test_unverified_guest_can_open_profile(self):
        self.client.force_login(make_user(username="opt_guest", role=User.Role.GUEST))
        self.assertEqual(self.client.get(reverse("account_profile")).status_code, 200)

    def test_guest_cabinet_is_minimal(self):
        self.client.force_login(make_user(username="opt_guest2", role=User.Role.GUEST))
        resp = self.client.get(reverse("account_profile"))
        self.assertContains(resp, reverse("account_resend_confirmation"))  # resend block shown
        self.assertNotContains(resp, reverse("account_api_token_regenerate"))  # API section hidden
        self.assertNotContains(resp, reverse("knowledge_submit"))  # submissions section hidden

    def test_verified_participant_sees_full_cabinet(self):
        user = make_user(username="opt_part", role=User.Role.PARTICIPANT)
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        self.client.force_login(user)
        resp = self.client.get(reverse("account_profile"))
        self.assertContains(resp, reverse("account_api_token_regenerate"))
        self.assertContains(resp, reverse("knowledge_submit"))
        self.assertNotContains(resp, reverse("account_resend_confirmation"))  # verified -> no resend


class SignupConfirmationRateLimitTests(TestCase):
    """The shared mail cooldown (last_mail_action_at) must also cover the first confirmation
    email allauth sends at signup, otherwise a fresh guest could immediately resend a second
    one and bypass the 10-minute limit."""

    def test_signup_stamps_last_mail_action_at(self):
        self.client.post(
            reverse("account_signup"),
            {"email": "stamp@example.com", "password1": "SuperPass123!", "password2": "SuperPass123!"},
        )
        user = User.objects.get(email="stamp@example.com")
        self.assertEqual(len(mail.outbox), 1)  # exactly one confirmation email at signup
        self.assertIsNotNone(user.last_mail_action_at)  # ...and the cooldown is recorded

    def test_resend_right_after_signup_is_rate_limited(self):
        self.client.post(
            reverse("account_signup"),
            {"email": "fresh@example.com", "password1": "SuperPass123!", "password2": "SuperPass123!"},
        )
        self.assertEqual(len(mail.outbox), 1)
        # The signup confirmation already stamped the cooldown, so an immediate resend is blocked.
        resp = self.client.post(reverse("account_resend_confirmation"))
        self.assertRedirects(resp, reverse("account_profile"))
        self.assertEqual(len(mail.outbox), 1)  # no second email within the cooldown window


class RepointUserForeignKeysTests(TestCase):
    """Regression for issue #124: production had user FKs pointing at the legacy auth_user
    table, raising IntegrityError -> 500 on image/document upload and page editing. The
    repair SQL must move a drifted FK back to accounts_user (idempotently) and must be a
    safe no-op when there is no auth_user table (fresh/CI database)."""

    def _fk_target(self, table, column):
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT confrelid::regclass::text
                FROM pg_constraint
                WHERE contype = 'f' AND conrelid = %s::regclass
                  AND conkey[1] = (
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = %s::regclass AND attname = %s
                  )
                """,
                [table, table, column],
            )
            row = cur.fetchone()
            return row[0] if row else None

    def _fk_name(self, table, column):
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE contype = 'f' AND conrelid = %s::regclass
                  AND conkey[1] = (
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = %s::regclass AND attname = %s
                  )
                """,
                [table, table, column],
            )
            return cur.fetchone()[0]

    def test_repoints_drifted_fk_back_to_accounts_user(self):
        from accounts.user_fk_repair import REPOINT_USER_FKS_SQL

        table, column = "wagtailimages_image", "uploaded_by_user_id"
        self.assertEqual(self._fk_target(table, column), "accounts_user")
        original = self._fk_name(table, column)
        with connection.cursor() as cur:
            # Reproduce the production drift: a legacy auth_user table and the FK on it.
            cur.execute("CREATE TABLE auth_user (id integer PRIMARY KEY)")
            cur.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{original}"')
            cur.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {table}_uploaded_by_fk_auth_user "
                f"FOREIGN KEY ({column}) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED"
            )
            self.assertEqual(self._fk_target(table, column), "auth_user")
            cur.execute(REPOINT_USER_FKS_SQL)
            cur.execute(REPOINT_USER_FKS_SQL)  # idempotent: second pass is a no-op
        self.assertEqual(self._fk_target(table, column), "accounts_user")

    def test_noop_when_auth_user_absent(self):
        from accounts.user_fk_repair import REPOINT_USER_FKS_SQL

        table, column = "wagtailimages_image", "uploaded_by_user_id"
        self.assertEqual(self._fk_target(table, column), "accounts_user")
        with connection.cursor() as cur:
            cur.execute(REPOINT_USER_FKS_SQL)  # must not raise on a healthy database
        self.assertEqual(self._fk_target(table, column), "accounts_user")


class DropLegacyAuthUserTests(TestCase):
    """Cleanup migration (#124): once user FKs are repointed, the legacy auth_user table
    and its m2m tables must be dropped, idempotently, and only when present."""

    def _table_exists(self, name):
        with connection.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", [name])
            return cur.fetchone()[0] is not None

    def test_drops_legacy_auth_user_and_its_m2m_tables(self):
        from accounts.user_fk_repair import DROP_LEGACY_AUTH_USER_SQL

        self.assertFalse(self._table_exists("auth_user"))  # fresh DB never had it
        with connection.cursor() as cur:
            cur.execute("CREATE TABLE auth_user (id integer PRIMARY KEY)")
            cur.execute(
                "CREATE TABLE auth_user_groups (id integer PRIMARY KEY, user_id integer REFERENCES auth_user(id))"
            )
            cur.execute(
                "CREATE TABLE auth_user_user_permissions "
                "(id integer PRIMARY KEY, user_id integer REFERENCES auth_user(id))"
            )
            self.assertTrue(self._table_exists("auth_user"))
            cur.execute(DROP_LEGACY_AUTH_USER_SQL)
            cur.execute(DROP_LEGACY_AUTH_USER_SQL)  # idempotent: second pass is a no-op
        self.assertFalse(self._table_exists("auth_user"))
        self.assertFalse(self._table_exists("auth_user_groups"))
        self.assertFalse(self._table_exists("auth_user_user_permissions"))

    def test_noop_when_auth_user_absent(self):
        from accounts.user_fk_repair import DROP_LEGACY_AUTH_USER_SQL

        with connection.cursor() as cur:
            cur.execute(DROP_LEGACY_AUTH_USER_SQL)  # must not raise on a healthy database
        self.assertFalse(self._table_exists("auth_user"))
