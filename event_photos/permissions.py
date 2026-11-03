"""Who sees and does what with event photos; the pages and the API both ask here."""

from django.db.models import Q
from django.utils.translation import gettext_noop

from accounts import managing
from calendar_app.models import Competition
from calendar_app.visibility import can_manage_or_own, can_see
from event_photos import actions


def can_see_event(user, competition: Competition) -> bool:
    if competition.is_deleted or competition.status != Competition.Status.APPROVED:
        return False
    return can_see(user, competition)


def can_manage_albums(user, competition: Competition) -> bool:
    """The event's creator, whatever their role, or an admin adds and refreshes its albums."""
    return can_manage_or_own(user, competition)


def can_represent(user, registration) -> bool:
    """Whether ``user`` manages the registrations and photos of the account the registration is
    (issue #315): a consent the member gave and the manager accepted, never a name or a team."""
    return bool(registration.user_id) and managing.acts_for(user, registration.user_id)


def looked_after(user) -> Q:
    """The registrations whose albums are the member's to look after: their own and those of the
    members whose registrations and photos they manage."""
    return Q(user=user) | Q(user_id__in=managing.member_ids(user))


def can_see_registration(user, registration) -> bool:
    """A registration's album: the account it belongs to, its representative, and the event's managers."""
    if not user.is_authenticated:
        return False
    return (
        registration.user_id == user.pk
        or can_represent(user, registration)
        or can_manage_albums(user, registration.competition)
    )


def can_mark(user, registration) -> bool:
    """Only the athlete (the registration's own account) or their representative marks photos."""
    return user.is_authenticated and (registration.user_id == user.pk or can_represent(user, registration))


def can_see_declared(user, declared) -> bool:
    """A bib a member named themselves: they and whoever manages their photos see its album, and no one
    marks it -- naming a bib finds photos, it gives no rights over them."""
    return user.is_authenticated and (declared.user_id == user.pk or managing.acts_for(user, declared.user_id))


def declared_bib_refusal(user, competition) -> str:
    """Why the member may not name their own bib at the event, in English for gettext; empty when they
    may: at an event with an indexed album, while the start lists bound no bib to their registration
    there. Searching the photos by a bib stays open to everybody either way."""
    if not actions.has_indexed_album(competition):
        return gettext_noop("This event has no indexed photo album yet.")
    if actions.has_bound_bib(user, competition):
        return gettext_noop("The start list already gives you a bib at this event.")
    return ""
