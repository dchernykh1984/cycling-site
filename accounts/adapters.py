from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.utils import timezone


class AccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.role = user.Role.GUEST
        if commit:
            user.save()
        return user

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        # Stamp the shared mail-rate-limit timestamp for *every* confirmation email,
        # including the very first one sent by allauth at signup. Otherwise a guest could
        # hit "resend" right after registering and send a second email past the cooldown.
        super().send_confirmation_mail(request, emailconfirmation, signup)
        user = emailconfirmation.email_address.user
        user.last_mail_action_at = timezone.now()
        user.save(update_fields=["last_mail_action_at"])

    def confirm_email(self, request, email_address):
        super().confirm_email(request, email_address)
        user = email_address.user
        if user.role == user.Role.GUEST:
            user.role = user.Role.PARTICIPANT
            user.save(update_fields=["role"])


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # save_user() is only called for new signups; upgrade existing guests here
        if not sociallogin.is_existing:
            return
        user = sociallogin.user
        has_verified = any(getattr(ea, "verified", False) for ea in sociallogin.email_addresses)
        if has_verified and user.role == user.Role.GUEST:
            user.role = user.Role.PARTICIPANT
            user.save(update_fields=["role"])

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        has_verified = any(getattr(ea, "verified", False) for ea in sociallogin.email_addresses)
        if has_verified and user.role == user.Role.GUEST:
            user.role = user.Role.PARTICIPANT
            user.save(update_fields=["role"])
        return user
