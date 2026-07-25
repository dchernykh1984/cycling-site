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


def strava_profile_url(account) -> str:
    """Public Strava profile URL of a just-authenticated athlete.

    The Strava provider stores the athlete id as the account's ``uid`` (see its ``extract_uid``),
    and the public profile lives at a fixed path built from that id. So this needs no extra API
    call and no extra scope -- it only reformats an identifier the OAuth response already gave us.
    """
    return f"https://www.strava.com/athletes/{account.uid}" if account.uid else ""


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        # Same hook (and therefore the same moment) that fills first/last name from the provider,
        # so a member signing up through Strava lands with their profile link already filled in.
        # Only ever set on a blank field, never overwriting a link the member typed themselves.
        user = super().populate_user(request, sociallogin, data)
        if sociallogin.account.provider == "strava" and not user.strava_link:
            user.strava_link = strava_profile_url(sociallogin.account)
        return user

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
