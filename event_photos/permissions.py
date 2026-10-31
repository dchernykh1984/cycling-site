"""Who sees and does what with event photos; the pages and the API both ask here."""

from django.db.models import Q

from accounts import managing
from calendar_app.models import Competition
from calendar_app.visibility import can_manage_or_own, can_see


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
