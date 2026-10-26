"""Who sees and does what with event photos; the pages and the API both ask here."""

from calendar_app.models import Competition
from calendar_app.visibility import can_see, manages


def can_see_event(user, competition: Competition) -> bool:
    if competition.is_deleted or competition.status != Competition.Status.APPROVED:
        return False
    return can_see(user, competition)


def can_manage_albums(user, competition: Competition) -> bool:
    """The event's creator, whatever their role, or an admin adds and refreshes its albums."""
    if manages(user, competition):
        return True
    return bool(user.is_authenticated and user.pk == competition.submitted_by_id)


def can_represent(user, registration) -> bool:
    """The coach / athlete-representative role of issue #315; False until that role exists."""
    return False


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
