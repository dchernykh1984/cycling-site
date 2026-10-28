"""Managing another member's registrations and event photos (issue #315): its rules in one place.

A member -- the manager -- hands out a link. Whoever opens it signed in may ask to be managed, and
the request waits until the manager accepts it. Either side ends it, and nothing is left behind.
Rights never pass along a chain: whom B manages is nothing to A, however A and B are linked.
"""

import uuid

from django.utils import timezone
from django.utils.translation import gettext

from .models import ManagedMember, ManagerInvite

# What opening a link comes to for the member who opened it
ASKED = "asked"
INVALID = "invalid"  # no such link, or one that ran out: the page says the same of both
OWN = "own"
MANAGED = "managed"
WAITING = "waiting"
UNCONFIRMED = "unconfirmed"  # the member's own address is not confirmed yet: they may only look


def acts_for(manager, member_id) -> bool:
    """Whether ``manager`` may act for the member with this id: an accepted request, not a waiting one."""
    if member_id is None or not getattr(manager, "is_authenticated", False):
        return False
    return ManagedMember.objects.filter(manager=manager, member_id=member_id, accepted_at__isnull=False).exists()


def member_ids(manager) -> set[int]:
    """The members ``manager`` may act for -- one query, for pages that ask about many rows."""
    if not getattr(manager, "is_authenticated", False):
        return set()
    return set(
        ManagedMember.objects.filter(manager=manager, accepted_at__isnull=False).values_list("member_id", flat=True)
    )


def invite_of(user) -> ManagerInvite | None:
    """The member's link, live or run out; None when they have none."""
    return ManagerInvite.objects.filter(manager=user).first()


def issue_invite(user) -> ManagerInvite:
    """A new link: the old key stops working at once, and requests already waiting stay."""
    invite, _created = ManagerInvite.objects.update_or_create(
        manager=user, defaults={"key": uuid.uuid4(), "created_at": timezone.now()}
    )
    return invite


def delete_invite(user) -> None:
    """No link at all, until the member makes a new one; requests already waiting stay."""
    ManagerInvite.objects.filter(manager=user).delete()


def find_invite(key) -> ManagerInvite | None:
    """The live link with this key, or None."""
    invite = ManagerInvite.objects.select_related("manager").filter(key=key).first()
    return invite if invite is not None and invite.is_valid() else None


def outcome_for(member, invite: ManagerInvite | None) -> str:
    """What asking through ``invite`` comes to for ``member``: ASKED, or why it cannot."""
    if invite is None:
        return INVALID
    if invite.manager_id == member.pk:
        return OWN
    row = ManagedMember.objects.filter(manager_id=invite.manager_id, member=member).first()
    if row is not None:
        return MANAGED if row.accepted_at else WAITING
    return ASKED


def refusal(outcome: str, invite: ManagerInvite | None) -> str:
    """Why asking through the link cannot be done, in the reader's language; empty when it can."""
    name = {"name": invite.manager.public_display_name} if invite is not None else {}
    if outcome == INVALID:
        return gettext("This link is not valid or has probably expired. Ask whoever sent it for a new one.")
    if outcome == OWN:
        return gettext("This is your own link: send it to the people whose registrations and photos you will manage.")
    if outcome == MANAGED:
        return gettext("%(name)s already manages your registrations and photos.") % name
    if outcome == WAITING:
        return gettext("Your request to %(name)s is already waiting to be accepted.") % name
    if outcome == UNCONFIRMED:
        return (
            gettext(
                "%(name)s asks to manage your registrations and photos. To answer, confirm your e-mail address"
                " first -- open the link in the mail we sent you -- and then open this link again."
            )
            % name
        )
    return ""


def ask(member, key) -> str:
    """The member asks, through the link with ``key``, to be managed by its owner."""
    invite = find_invite(key)
    outcome = outcome_for(member, invite)
    if outcome == ASKED and invite is not None:
        ManagedMember.objects.get_or_create(manager_id=invite.manager_id, member=member)
    return outcome


def waiting(manager):
    """Requests waiting for ``manager``, oldest first, with the members who sent them."""
    return (
        ManagedMember.objects.filter(manager=manager, accepted_at__isnull=True)
        .select_related("member")
        .order_by("created_at", "pk")
    )


def members(manager):
    """The members ``manager`` acts for, by name."""
    return (
        ManagedMember.objects.filter(manager=manager, accepted_at__isnull=False)
        .select_related("member")
        .order_by("member__last_name", "member__first_name", "member_id")
    )


def managers(member):
    """Who manages ``member`` or is asked to, the accepted first."""
    return (
        ManagedMember.objects.filter(member=member)
        .select_related("manager")
        .order_by("accepted_at", "created_at", "pk")
    )


def accept(manager, member_id) -> bool:
    return bool(
        ManagedMember.objects.filter(manager=manager, member_id=member_id, accepted_at__isnull=True).update(
            accepted_at=timezone.now()
        )
    )


def reject(manager, member_id) -> bool:
    """A rejected request just disappears; the member may ask again through a live link."""
    deleted, _ = ManagedMember.objects.filter(manager=manager, member_id=member_id, accepted_at__isnull=True).delete()
    return bool(deleted)


def accept_all(manager) -> int:
    return ManagedMember.objects.filter(manager=manager, accepted_at__isnull=True).update(accepted_at=timezone.now())


def reject_all(manager) -> int:
    deleted, _ = ManagedMember.objects.filter(manager=manager, accepted_at__isnull=True).delete()
    return deleted


def drop(manager, member_id) -> bool:
    """The manager stops managing a member."""
    deleted, _ = ManagedMember.objects.filter(manager=manager, member_id=member_id, accepted_at__isnull=False).delete()
    return bool(deleted)


def leave(member, manager_id) -> bool:
    """The member ends a manager's right, or withdraws the request still waiting."""
    deleted, _ = ManagedMember.objects.filter(manager_id=manager_id, member=member).delete()
    return bool(deleted)
