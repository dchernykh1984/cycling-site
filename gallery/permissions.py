"""Who may do what in the gallery.

Organizers and up create albums and fill them; an organizer manages the albums they created, an
admin manages every album. Everybody else only looks.
"""

from accounts.models import User

_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)
_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def is_admin_plus(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK))


def can_create_album(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ORGANIZER_RANK))


def can_manage_album(user, album) -> bool:
    if is_admin_plus(user):
        return True
    return can_create_album(user) and album.created_by_id == user.pk
