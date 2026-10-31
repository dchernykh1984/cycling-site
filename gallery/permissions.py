"""Who may do what in the gallery.

The gallery keeps the club's best moments, chosen by the people who run the site: admins and the
owner create albums, fill them and pick their covers. Everybody else -- organizers included -- only
looks. Organizers publish their own events and results; the gallery is curated, not open to them.
"""

from accounts import roles


def can_create_album(user) -> bool:
    return roles.at_least(user, roles.MANAGE_GALLERY)


def can_manage_album(user, album) -> bool:
    """Every album is the site's: any admin may change any of them, whoever created it."""
    return roles.at_least(user, roles.MANAGE_GALLERY)
