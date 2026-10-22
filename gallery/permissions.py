"""Who may do what in the gallery.

The gallery keeps the club's best moments, chosen by the people who run the site: admins and the
owner create albums, fill them and pick their covers. Everybody else -- organizers included -- only
looks. Organizers publish their own events and results; the gallery is curated, not open to them.
"""

from accounts.models import User

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def is_admin_plus(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK))


def can_create_album(user) -> bool:
    return is_admin_plus(user)


def can_manage_album(user, album) -> bool:
    """Every album is the site's: any admin may change any of them, whoever created it."""
    return is_admin_plus(user)
