"""Who may see an event. The one place the site's own pages ask.

Three things keep a published event out of sight, each with its own audience:

* deleted -- nobody;
* hidden -- taken down by a manager: admins and up in the listings, and whoever manages the event
  on its own page;
* invite-only (issue #313) -- the people who may edit it (its author while an organizer, admins,
  owners) and everybody who opened its invitation link while signed in.

Channels read by machines and cached for everyone -- the sitemap, the feeds, IndexNow, the landing
pages, the public API -- never carry an invite-only event, whoever is asking; they filter on the
flag directly rather than through here.
"""

from django.db.models import Q, QuerySet

from accounts.models import User

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)


def is_admin_plus(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK))


def manages(user, competition) -> bool:
    """Whether ``user`` may manage this event: admins and up, or its author while an organizer."""
    if is_admin_plus(user):
        return True
    return bool(user.is_authenticated and user.get_role_rank() >= _ORGANIZER_RANK and user == competition.submitted_by)


def _let_in(user) -> Q:
    """Events this signed-in user was let into: by opening the link, or by being registered.

    A registration counts because an event can turn invite-only after people signed up for it while
    it was public, and its own riders must not lose the page of the race they are entered in.
    """
    from calendar_app.models import CompetitionInvite
    from registrations.models import CompetitionRegistration

    invited = CompetitionInvite.objects.filter(user=user).values("competition_id")
    registered = CompetitionRegistration.objects.filter(user=user, is_rejected=False).values("competition_id")
    return Q(pk__in=invited) | Q(pk__in=registered)


def is_invited(user, competition) -> bool:
    from calendar_app.models import Competition

    return bool(user.is_authenticated and Competition.objects.filter(_let_in(user), pk=competition.pk).exists())


def can_see(user, competition) -> bool:
    """Whether ``user`` may see this published event's own page, and everything hung off it."""
    if competition.is_hidden and not manages(user, competition):
        return False
    if competition.invite_only and not (manages(user, competition) or is_invited(user, competition)):
        return False
    return True


def can_review(user, competition) -> bool:
    """Whether ``user`` may see an event awaiting review: its author, or a moderator.

    Any organizer moderates, but an invite-only event is for the people who may edit it -- so while
    it waits, only admins and up review it.
    """
    if user.is_authenticated and user == competition.submitted_by:
        return True
    if competition.invite_only:
        return is_admin_plus(user)
    return bool(user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ORGANIZER_RANK))


def listed_for(qs: QuerySet, user) -> QuerySet:
    """The published events in ``qs`` that ``user`` may see in a listing."""
    if is_admin_plus(user):
        return qs
    qs = qs.filter(is_hidden=False)
    let_in = Q(invite_only=False)
    if user.is_authenticated:
        let_in |= _let_in(user)
        if user.get_role_rank() >= _ORGANIZER_RANK:
            let_in |= Q(submitted_by=user)
    return qs.filter(let_in)
