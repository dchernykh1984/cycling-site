"""The accounts the site's own agents post through (issue #436): an owner marks them, and what they post is
nobody's work to judge -- their events carry no organizer's rating. Until one is marked, the owners are
asked to mark it on every page."""

from django.db.models import Q

from accounts.models import User


def marked():
    """The accounts marked as the site's own."""
    return User.objects.filter(is_service_account=True)


def candidates():
    """The accounts an owner chooses among: those with an API token -- an agent posts through one -- and
    those marked already, so a mark can be taken back from an account whose token is gone."""
    return User.objects.filter(Q(api_token__isnull=False) | Q(is_service_account=True)).order_by(
        "last_name", "first_name", "email", "pk"
    )


def mark(chosen_ids) -> None:
    """Exactly the candidates in ``chosen_ids`` marked; nobody outside the candidates is touched."""
    pool = candidates()
    pool.filter(pk__in=chosen_ids).update(is_service_account=True)
    pool.exclude(pk__in=chosen_ids).update(is_service_account=False)


def set_marked(user_id: int, on: bool) -> bool:
    """One candidate marked or not; False when ``user_id`` is no candidate."""
    return bool(candidates().filter(pk=user_id).update(is_service_account=on))
