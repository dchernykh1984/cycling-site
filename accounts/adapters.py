import ipaddress
import logging
import threading

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.strava.provider import StravaProvider
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import get_language, get_language_from_path
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)
# Set once this process has logged where it reads a visitor's address from (once, after each start)
_address_source_logged = threading.Event()


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

    def get_client_ip(self, request):
        """The visitor's own address, which allauth's sign-in limits count by.

        Behind a proxy the connection comes from the proxy, one address for everyone, and a limit
        counted by it holds the whole site back. The proxy names the visitor in a header the deployment
        names (CLIENT_IP_HEADER); without one, or with a value that is no address, the connection's
        address counts, as before.
        """
        header = settings.CLIENT_IP_HEADER
        named = request.headers.get(header, "").strip() if header else ""
        _log_address_source(header, named, request.META.get("REMOTE_ADDR", ""))
        if named:
            try:
                return _visitor(ipaddress.ip_address(named))
            except ValueError:
                logger.warning("%s holds no address; sign-in limits count the connection's instead", header)
        return super().get_client_ip(request)

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


def _visitor(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Who a limit counts: an IPv4 address, or an IPv6 one's /64 -- a subscriber is handed a whole /64
    and could take a new address from it for every try."""
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped:
        return str(ip.ipv4_mapped)
    return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)


def _log_address_source(header: str, named: str, remote: str) -> None:
    """Once a process: where the visitor's address came from, cut to its network, so a look at the log
    after a deploy tells a visitor's address from a proxy's without keeping anybody's."""
    if _address_source_logged.is_set():
        return
    _address_source_logged.set()
    source = f"the {header} header: {_network(named)}" if header else "the connection only"
    logger.info("Sign-in limits count visitors by %s; the connection: %s", source, _network(remote))


def _network(address: str) -> str:
    """An address cut to its /16 (IPv4) or /48 (IPv6), and whether it is a private one."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "malformed" if address else "none"
    network = ipaddress.ip_network(f"{ip}/{16 if ip.version == 4 else 48}", strict=False)
    return f"{network} ({'private' if ip.is_private else 'public'})"


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
        if sociallogin.account.provider == StravaProvider.id and not user.strava_link:
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
        # A provider's account has no sign-up form to ask on: the first sign-in asks instead
        # (accounts.middleware). allauth's form for a provider that left a gap asks it there, and
        # its answer, saved right after this, clears the flag.
        user.privacy_consent_pending = True
        user.save(update_fields=["privacy_consent_pending"])
        return user
