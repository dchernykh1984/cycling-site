"""Handing a person without an account over (issue #438): its rules in one place.

The person's manager makes a link, to the owner or to a mentor, and sends it. Whoever opens it signed in
asks, by a button, to take the person over; nothing moves until the manager confirms that the account
is the one they meant.

To the owner: the person's entries and named bibs go into the account -- the person's own --, its empty
profile fields are filled from the person, and the person leaves the manager's list; the account may
let the manager go on managing its registrations and photos.

To a mentor -- another coach, a parent: the person stays a person without an account, with their entries
and named bibs, in the mentor's list instead of the manager's. The mentor gives the same word about the
person's personal data as anybody who adds people, and needs room for one more and no copy of them.

An account may take over several people, from several managers.
"""

import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from accounts import virtual_members
from accounts.models import ManagedMember, VirtualMember, VirtualMemberTransfer

# What opening a link comes to for the account that opened it
ASKED = "asked"
INVALID = "invalid"  # no such link, one that ran out, or one somebody asked through already: said alike
OWN = "own"  # the link of a person the account itself added
UNCONFIRMED = "unconfirmed"  # the account's address is not confirmed yet: it may only look
NO_WORD = "no_word"  # to a mentor who has not said yet that they may handle such people's data
FULL = "full"  # to a mentor whose list has no room for one more
COPY = "copy"  # to a mentor who has the person already: the same names and date of birth

To = VirtualMemberTransfer.To

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


def why_no_link(owner) -> str:
    """Why ``owner`` may not hand a person over, in the reader's language; empty when they may. Whoever
    opens the link has to see who hands the person over, so a member without a name is asked for one."""
    if owner.first_name.strip() and owner.last_name.strip():
        return ""
    return gettext(
        "Add your first and last name to your profile first: whoever opens the link must see who hands the person over."
    )


class RefusedError(Exception):
    """A request the manager cannot answer yes to now; the reason, in the reader's language, is the message."""


def issue(person: VirtualMember, to: str = To.OWNER) -> VirtualMemberTransfer:
    """A new link for ``person``, to the owner or to a mentor: the old key stops working at once, whatever
    it was for, and a request waiting is dropped."""
    link, _created = VirtualMemberTransfer.objects.update_or_create(
        person=person,
        defaults={
            "key": uuid.uuid4(),
            "created_at": timezone.now(),
            "claimed_by": None,
            "claimed_at": None,
            "keep_manager": False,
            "to": to,
        },
    )
    return link


def find(key) -> VirtualMemberTransfer | None:
    """The live link with this key -- within its week, nobody has asked through it -- or None."""
    link = VirtualMemberTransfer.objects.select_related("person__owner").filter(key=key).first()
    return link if link is not None and link.is_live() else None


def mentor_refusal(account, person: VirtualMember) -> str:
    """Why ``account`` cannot take ``person`` into its list as their mentor -- FULL or COPY --; empty when it can."""
    if virtual_members.room(account) == 0:
        return FULL
    if virtual_members.copy_of(account, person.last_name, person.first_name, person.birth_date):
        return COPY
    return ""


def outcome_for(account, link: VirtualMemberTransfer | None) -> str:
    """What asking through ``link`` comes to for ``account``: ASKED, or why it cannot."""
    if link is None:
        return INVALID
    if link.person.owner_id == account.pk:
        return OWN
    if link.to_mentor:
        return mentor_refusal(account, link.person) or ASKED
    return ASKED


def refusal(outcome: str, link: VirtualMemberTransfer | None) -> str:
    """Why taking the person over cannot be asked, in the reader's language; empty when it can."""
    if outcome == INVALID:
        return gettext("This link is not valid, has expired or has been used. Ask whoever sent it for a new one.")
    if outcome == OWN and link is not None and link.to_mentor:
        return gettext("This is the link of a person you added: send it to the mentor who takes them over.")
    if outcome == OWN:
        return gettext(
            "This is the link of a person you added: send it to the owner of the account their data moves to."
        )
    if outcome == NO_WORD and link is not None:
        return gettext(
            "Confirm first that you may handle the personal data of %(person)s: you have their consent, or their"
            " legal representative's."
        ) % {"person": link.person}
    if outcome == FULL and link is not None:
        return gettext(
            "Your list of people without an account is full, so %(person)s cannot join it. Delete somebody from it"
            " first."
        ) % {"person": link.person}
    if outcome == COPY and link is not None:
        return gettext("You already have %(person)s, born on %(date)s, in your list of people without an account.") % {
            "person": link.person,
            "date": link.person.birth_date.strftime("%d.%m.%Y"),
        }
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
    request: of two opened at once, the second finds it used. A mentor must have given their word about
    such people's data first; the box that keeps the manager is the owner's alone."""
    with transaction.atomic():
        link = (
            VirtualMemberTransfer.objects.select_for_update(of=("self",))
            .select_related("person__owner")
            .filter(key=key)
            .first()
        )
        live = link if link is not None and link.is_live() else None
        outcome = outcome_for(account, live)
        if outcome == ASKED and live is not None and live.to_mentor and not virtual_members.consented(account):
            outcome = NO_WORD
        if outcome == ASKED and live is not None:
            keep_manager = keep_manager and not live.to_mentor
            live.claimed_by, live.claimed_at, live.keep_manager = account, timezone.now(), keep_manager
            live.save(update_fields=["claimed_by", "claimed_at", "keep_manager"])
    return outcome


def confirm(owner, person_id) -> VirtualMemberTransfer | None:
    """``owner`` confirms the request waiting for one of their people, which hands the person over;
    the request as it was -- the person and the account in memory -- or None when none waits. A mentor
    whose list has filled up, or come to hold the person, since they asked is refused: ``RefusedError``."""
    with transaction.atomic():
        link = (
            VirtualMemberTransfer.objects.select_for_update(of=("self",))
            .select_related("person", "claimed_by")
            .filter(person__owner=owner, person_id=person_id, claimed_by__isnull=False)
            .first()
        )
        if link is None:
            return None
        if link.to_mentor:
            why = mentor_refusal(link.claimed_by, link.person)
            if why:
                raise RefusedError(_stays(why, link.person, link.claimed_by))
            move_to_mentor(link.person, link.claimed_by)
        else:
            hand_over(link.person, link.claimed_by, manager=owner if link.keep_manager else None)
        return link


def _stays(why: str, person: VirtualMember, mentor) -> str:
    """Why ``person`` stays with their manager, told to the manager."""
    names = {"name": mentor.public_display_name, "person": person}
    if why == FULL:
        return gettext("%(name)s has no room left for people without an account, so %(person)s stays with you.") % names
    return gettext("%(name)s already has %(person)s in their list, so they stay with you.") % names


def cancel(owner, person_id) -> bool:
    """``owner`` takes back the link of one of their people that nobody has asked through: it stops working, and
    the person may be handed over again, either way. A request already waiting is answered instead."""
    deleted, _ = VirtualMemberTransfer.objects.filter(
        person__owner=owner, person_id=person_id, claimed_by__isnull=True
    ).delete()
    return bool(deleted)


def reject(owner, person_id) -> bool:
    """The request goes, and its link with it: the manager makes a new link to try again."""
    deleted, _ = VirtualMemberTransfer.objects.filter(
        person__owner=owner, person_id=person_id, claimed_by__isnull=False
    ).delete()
    return bool(deleted)


def move_to_mentor(person: VirtualMember, account) -> None:
    """``person`` goes, as they are, into ``account``'s list of people without an account: their entries and
    named bibs stay theirs, and so come with them; the link goes."""
    person.owner = account
    person.save(update_fields=["owner"])
    VirtualMemberTransfer.objects.filter(person=person).delete()


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
