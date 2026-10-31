"""Who may see an event. The one place the site's own pages ask.

Three things keep a published event out of sight, each with its own audience:

* deleted -- nobody;
* hidden -- taken down by a manager: admins and up in the listings, and whoever manages the event
  on its own page;
* invite-only (issue #313) -- the people who may edit it (its author while an organizer, admins,
  owners) and everybody who opened its invitation link while signed in.

Channels read by machines and cached for everyone -- the sitemap, the feeds, IndexNow, the landing
pages, the gallery's choices -- never carry an invite-only event, whoever is asking: they ask
``public_events`` here, which leaves out all three.
"""

from django.db.models import Q, QuerySet

from accounts import roles


def public_events_q(through: str = "") -> Q:
    """What makes an event public: approved, and neither deleted, hidden nor invite-only. ``through``
    reaches the event over a relation, as ``"competition__"`` does from a registration."""
    from calendar_app.models import Competition

    return Q(
        **{
            f"{through}status": Competition.Status.APPROVED,
            f"{through}is_deleted": False,
            f"{through}is_hidden": False,
            f"{through}invite_only": False,
        }
    )


def public_events() -> QuerySet:
    """The events every channel may carry for anybody, unordered."""
    from calendar_app.models import Competition

    return Competition.objects.filter(public_events_q())


def is_public(competition) -> bool:
    """``public_events_q`` for one event in hand."""
    return (
        competition.status == competition.Status.APPROVED
        and not competition.is_deleted
        and not competition.is_hidden
        and not competition.invite_only
    )


def manages(user, competition) -> bool:
    """Whether ``user`` may manage this event: admins and up, or its author while an organizer."""
    if roles.at_least(user, roles.MANAGE_ALL_EVENTS):
        return True
    return roles.at_least(user, roles.PUBLISH_EVENTS) and user.pk == competition.submitted_by_id


def can_manage_or_own(user, competition) -> bool:
    """A manager of the event, or its author whatever their role and its status (FR-EVT-002): who
    edits, deletes and resubmits it -- even a participant their own rejected event (#200) -- holds
    its upload token and keeps its photo albums."""
    if manages(user, competition):
        return True
    return user.is_authenticated and user.pk == competition.submitted_by_id


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
    if user.is_authenticated and user.pk == competition.submitted_by_id:
        return True
    if competition.invite_only:
        return roles.at_least(user, roles.MANAGE_ALL_EVENTS)
    return roles.at_least(user, roles.MODERATE_EVENTS)


def can_open(user, competition) -> bool:
    """Whether ``user`` may open this event's own page, and its calendar file (issue #398).

    A not-yet-approved event is its author's and its moderators' -- so they can track a submission and
    read a rejection reason -- a published one whoever can see it, a deleted one nobody's.
    """
    from calendar_app.models import Competition

    if competition.is_deleted:
        return False
    if competition.status != Competition.Status.APPROVED:
        return can_review(user, competition)
    return can_see(user, competition)


def listed_for(qs: QuerySet, user) -> QuerySet:
    """The published events in ``qs`` that ``user`` may see in a listing."""
    if roles.at_least(user, roles.MANAGE_ALL_EVENTS):
        return qs
    qs = qs.filter(is_hidden=False)
    let_in = Q(invite_only=False)
    if user.is_authenticated:
        let_in |= _let_in(user)
        if roles.at_least(user, roles.PUBLISH_EVENTS):
            let_in |= Q(submitted_by=user)
    return qs.filter(let_in)
