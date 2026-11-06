"""Handing a person without an account over to an account of their own (issue #438): its rules in one place.

The person's manager makes a link and sends it. Whoever opens it signed in asks, by a button, to take
the person over -- and may let the manager go on managing their registrations and photos. Nothing
moves until the manager confirms that the account is their person's: then the person's entries and
named bibs go to the account, the account's empty profile fields are filled from the person, and the
person leaves the manager's list. An account may take over several people, from several managers.
"""

import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from accounts.models import ManagedMember, VirtualMember, VirtualMemberTransfer

# What opening a link comes to for the account that opened it
ASKED = "asked"
INVALID = "invalid"  # no such link, one that ran out, or one somebody asked through already: said alike
OWN = "own"  # the link of a person the account itself added
UNCONFIRMED = "unconfirmed"  # the account's address is not confirmed yet: it may only look

#: The person's data an account takes where its own profile has none, under the profile's own names
PROFILE_FIELDS = (
    "last_name",
    "first_name",
    "gender",
    "birth_date",
    "team",
    "city",
    "strava_link",
    "sports_achievements",
)
#: The person's fields that are not theirs to hand over: the row's id and the manager it belongs to
NOT_HANDED_OVER = ("id", "owner")
#: What points at a person and what ``hand_over`` does with it: their entries and named bibs go to the
#: account, the link goes with the person. A table that comes to point at people fails a test until it is
#: named here -- and handed over there.
HANDED_OVER = ("registrations", "declared_bibs")
GONE_WITH_THE_PERSON = ("transfer",)


def links_of(owner):
    """The links and requests of the people ``owner`` added, with the accounts that asked."""
    return VirtualMemberTransfer.objects.filter(person__owner=owner).select_related("claimed_by")


def issue(person: VirtualMember) -> VirtualMemberTransfer:
    """A new link for ``person``: the old key stops working at once, and a request waiting is dropped."""
    link, _created = VirtualMemberTransfer.objects.update_or_create(
        person=person,
        defaults={
            "key": uuid.uuid4(),
            "created_at": timezone.now(),
            "claimed_by": None,
            "claimed_at": None,
            "keep_manager": False,
        },
    )
    return link


def find(key) -> VirtualMemberTransfer | None:
    """The live link with this key -- within its week, nobody has asked through it -- or None."""
    link = VirtualMemberTransfer.objects.select_related("person__owner").filter(key=key).first()
    return link if link is not None and link.is_live() else None


def outcome_for(account, link: VirtualMemberTransfer | None) -> str:
    """What asking through ``link`` comes to for ``account``: ASKED, or why it cannot."""
    if link is None:
        return INVALID
    if link.person.owner_id == account.pk:
        return OWN
    return ASKED


def refusal(outcome: str, link: VirtualMemberTransfer | None) -> str:
    """Why taking the person over cannot be asked, in the reader's language; empty when it can."""
    if outcome == INVALID:
        return gettext("This link is not valid, has expired or has been used. Ask whoever sent it for a new one.")
    if outcome == OWN:
        return gettext(
            "This is the link of a person you added: send it to the owner of the account their data moves to."
        )
    if outcome == UNCONFIRMED and link is not None:
        return gettext(
            "%(name)s hands %(person)s over to you. To answer, confirm your e-mail address first -- open the"
            " link in the mail we sent you -- and then open this link again."
        ) % {"name": link.person.owner.public_display_name, "person": link.person}
    return ""


def fills(person: VirtualMember, account) -> list[str]:
    """The fields of ``account``'s profile that ``person`` would fill: empty there, filled in here."""
    return [name for name in PROFILE_FIELDS if not getattr(account, name) and getattr(person, name)]


def ask(account, key, keep_manager: bool) -> str:
    """``account`` asks, through the link with ``key``, to take its person over. The link takes one
    request: of two opened at once, the second finds it used."""
    with transaction.atomic():
        link = (
            VirtualMemberTransfer.objects.select_for_update(of=("self",))
            .select_related("person__owner")
            .filter(key=key)
            .first()
        )
        live = link if link is not None and link.is_live() else None
        outcome = outcome_for(account, live)
        if outcome == ASKED and live is not None:
            live.claimed_by, live.claimed_at, live.keep_manager = account, timezone.now(), keep_manager
            live.save(update_fields=["claimed_by", "claimed_at", "keep_manager"])
    return outcome


def confirm(owner, person_id) -> VirtualMemberTransfer | None:
    """``owner`` confirms the request waiting for one of their people, which hands the person over;
    the request as it was -- the person and the account in memory -- or None when none waits."""
    with transaction.atomic():
        link = (
            VirtualMemberTransfer.objects.select_for_update(of=("self",))
            .select_related("person", "claimed_by")
            .filter(person__owner=owner, person_id=person_id, claimed_by__isnull=False)
            .first()
        )
        if link is None:
            return None
        hand_over(link.person, link.claimed_by, manager=owner if link.keep_manager else None)
        return link


def reject(owner, person_id) -> bool:
    """The request goes, and its link with it: the manager makes a new link to try again."""
    deleted, _ = VirtualMemberTransfer.objects.filter(
        person__owner=owner, person_id=person_id, claimed_by__isnull=False
    ).delete()
    return bool(deleted)


def hand_over(person: VirtualMember, account, manager=None) -> None:
    """Everything of ``person`` goes to ``account``, and the person is gone: the profile fields the
    account has empty, the entries -- an event both are entered for keeps both entries -- and the
    named bibs, a number the account named at the same event once. ``manager``, when given, goes on
    managing the account's registrations and photos."""
    from event_photos.models import DeclaredBib
    from registrations.models import CompetitionRegistration

    with transaction.atomic():
        filled = fills(person, account)
        for name in filled:
            setattr(account, name, getattr(person, name))
        if filled:
            account.save(update_fields=filled)
        # One by one, not in one update: the audit log records each entry that changes hands
        for entry in CompetitionRegistration.objects.filter(virtual_member=person):
            entry.user, entry.virtual_member = account, None
            entry.save(update_fields=["user", "virtual_member"])
        for named in DeclaredBib.objects.filter(virtual_member=person):
            if DeclaredBib.objects.filter(user=account, competition_id=named.competition_id, bib=named.bib).exists():
                named.delete()
            else:
                named.user, named.virtual_member = account, None
                named.save(update_fields=["user", "virtual_member"])
        if manager is not None and manager.pk != account.pk:
            row, _created = ManagedMember.objects.get_or_create(
                manager=manager, member=account, defaults={"accepted_at": timezone.now()}
            )
            if row.accepted_at is None:
                row.accepted_at = timezone.now()
                row.save(update_fields=["accepted_at"])
        person.delete()
