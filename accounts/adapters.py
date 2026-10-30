from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import get_language, get_language_from_path
from django.utils.translation import gettext_lazy as _


def _with_language(url: str) -> str:
    """A path of this site that has no language, under the language of the page being answered.

    A `next` that carries its language, or another site's address, is left as it is.
    """
    if url.startswith("/") and not url.startswith("//") and not get_language_from_path(url):
        return f"/{get_language()}{url}"
    return url


def _in_page_language(url: str, request) -> str:
    """A path without a language, in the language of the page the member signed in on.

    The settings name the bare "/", which goes on to the language the reader chose -- in their profile
    or with the language buttons -- and, without a choice, to one picked from the browser: a member who
    signed in on the Kazakh page with a Russian browser landed on the Russian home page. A choice still
    wins, as it does for any address without a language.
    """
    user = getattr(request, "user", None)
    chosen = getattr(user, "is_authenticated", False) and getattr(user, "preferred_language", "")
    if chosen or request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME):
        return url
    return _with_language(url)


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        return _in_page_language(super().get_login_redirect_url(request), request)

    def get_logout_redirect_url(self, request):
        # The home page in the language that was being read: signed out, the reader is a guest, and a
        # bare address would go by the browser or an old cookie -- never by the profile just left.
        return _with_language(super().get_logout_redirect_url(request))

    def get_signup_redirect_url(self, request):
        return _in_page_language(super().get_signup_redirect_url(request), request)

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


def user_display(user) -> str:
    """How allauth names a member back to them -- "Successfully signed in as ...", and its emails.

    allauth's default is the username, which here is an internal handle nobody chose: members sign
    in by email, and it was showing a lowercased "denis" to a member whose profile says Denis
    Chernykh. The name from the profile comes first, then the address they sign in with.
    """
    return user.get_full_name().strip() or user.email or user.get_username()


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

    def validate_disconnect(self, account, accounts):
        # allauth already refuses to unlink the last provider when the account has no usable
        # password -- but it does not check for an email address, and sign-in here is by email.
        # Without this, a member who signed up through Strava, then set a password, could unlink
        # Strava and be left with a password but no address to sign in with, i.e. locked out.
        super().validate_disconnect(account, accounts)
        others_remain = any(other.pk != account.pk for other in accounts)
        if not others_remain and not account.user.can_sign_in_with_password():
            raise ValidationError(
                _("Add an email address and a password first, otherwise you would have no way to sign in.")
            )

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
