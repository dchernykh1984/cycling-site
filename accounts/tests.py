import re
from unittest.mock import MagicMock, patch

from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse

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
        self.assertTrue(user.groups.filter(name="participants").exists())

    def test_organizer_role_creates_and_assigns_group(self):
        user = make_user(role=User.Role.ORGANIZER)
        self.assertTrue(user.groups.filter(name="organizers").exists())

    def test_guest_role_has_no_managed_group(self):
        user = make_user(role=User.Role.GUEST)
        managed = set(ROLE_GROUP_MAP.values())
        self.assertFalse(user.groups.filter(name__in=managed).exists())

    def test_role_change_swaps_group(self):
        user = make_user(role=User.Role.PARTICIPANT)
        self.assertTrue(user.groups.filter(name="participants").exists())

        user.role = User.Role.ORGANIZER
        user.save()

        self.assertFalse(user.groups.filter(name="participants").exists())
        self.assertTrue(user.groups.filter(name="organizers").exists())

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
        self.assertEqual(user.groups.filter(name="participants").count(), 1)

    def test_sync_removes_stale_group_when_group_deleted(self):
        user = make_user(role=User.Role.PARTICIPANT)
        Group.objects.filter(name="participants").delete()
        user.role = User.Role.GUEST
        user.save()
        managed = set(ROLE_GROUP_MAP.values())
        self.assertFalse(user.groups.filter(name__in=managed).exists())

    def test_sync_cleans_stale_groups_when_target_already_present(self):
        user = make_user(role=User.Role.PARTICIPANT)
        admins_group, _ = Group.objects.get_or_create(name="admins")
        user.groups.add(admins_group)
        _sync_user_group(user)
        self.assertTrue(user.groups.filter(name="participants").exists())
        self.assertFalse(user.groups.filter(name="admins").exists())


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
        self.assertContains(response, "not confirmed")

    def test_profile_hides_unverified_warning_when_email_confirmed(self):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_profile"))
        self.assertNotContains(response, "not confirmed")


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
        view = self._make_view(User.Role.OWNER)
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
