"""People without accounts a member enters for starts and looks after the event photos of (issue #438).

Only their manager sees and changes them. Adding anyone takes the manager's word, given once and for
good, that they may handle these people's personal data; how many they may add is a rule of roles.py.
A person taken off the site keeps their past races in the results and is entered in none to come.
"""

from django.db.models import Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from accounts import roles
from accounts.models import VirtualMember

#: The most people one request adds, whatever the manager may add in all
BATCH_LIMIT = 1000


def consented(user) -> bool:
    return user.virtual_members_consent_at is not None


def consent(user) -> None:
    """The manager's word that they may handle the personal data of the people they add."""
    if user.virtual_members_consent_at is None:
        user.virtual_members_consent_at = timezone.now()
        user.save(update_fields=["virtual_members_consent_at"])


def of(owner):
    """The people ``owner`` added, by name."""
    return VirtualMember.objects.filter(owner=owner)


def room(owner) -> int | None:
    """How many more people ``owner`` may add: None for any number."""
    limit = roles.virtual_members_limit(owner)
    return None if limit is None else max(0, limit - of(owner).count())


def added_by(user, virtual_member_id) -> bool:
    """Whether the person without an account with this id is one ``user`` added."""
    return virtual_member_id is not None and of(user).filter(pk=virtual_member_id).exists()


def find(owner, virtual_member_id) -> VirtualMember | None:
    """The person with this id if ``owner`` added them; None for anybody else's, as for nobody's, and
    for an id that is no number."""
    if not str(virtual_member_id).isdecimal():
        return None
    return of(owner).filter(pk=int(virtual_member_id)).first()


def who(person) -> dict:
    """Where an entry or a named bib keeps ``person``: an account, or a person without one."""
    return {"virtual_member": person} if isinstance(person, VirtualMember) else {"user": person}


def key(last_name: str, first_name: str, birth_date) -> tuple:
    """What makes two of a manager's people one: the same names and date of birth, whatever the case."""
    return (last_name.strip().casefold(), first_name.strip().casefold(), birth_date)


def races_to_come() -> Q:
    """Entries in events that have not started yet, from a registration's side. A race run today, or a
    stage race under way, keeps its entries: its start lists and results may already hold them."""
    return Q(competition__date_start__gt=timezone.localdate())


@receiver(pre_delete, sender=VirtualMember)
def _withdraw_from_races_to_come(sender, instance, **kwargs):
    """Taken off the site -- by their manager, or with the manager's account -- a person is entered in
    no race to come; their past ones stay in the results, as anybody's whose account is gone."""
    from registrations.models import CompetitionRegistration

    CompetitionRegistration.objects.filter(races_to_come(), virtual_member=instance).delete()
