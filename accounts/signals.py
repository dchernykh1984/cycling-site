from allauth.account.signals import email_confirmed
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User

ROLE_GROUP_MAP: dict[str, str] = {
    User.Role.PARTICIPANT: "participants",
    User.Role.ORGANIZER: "organizers",
    User.Role.ADMIN: "admins",
    User.Role.OWNER: "owners",
}


@receiver(email_confirmed)
def assign_participant_on_email_confirmed(sender, request, email_address, **kwargs):
    user = email_address.user
    if user.role == User.Role.GUEST:
        user.role = User.Role.PARTICIPANT
        user.save(update_fields=["role"])  # post_save triggers _sync_user_group


@receiver(post_save, sender=User)
def sync_role_to_group(sender, instance, **kwargs):
    _sync_user_group(instance)


def _sync_user_group(user: User) -> None:
    target_group_name = ROLE_GROUP_MAP.get(user.role)
    managed_group_names = set(ROLE_GROUP_MAP.values())
    current_managed = set(user.groups.filter(name__in=managed_group_names).values_list("name", flat=True))

    stale = current_managed - ({target_group_name} if target_group_name else set())
    if stale:
        user.groups.remove(*Group.objects.filter(name__in=stale))

    if target_group_name and target_group_name not in current_managed:
        group, _ = Group.objects.get_or_create(name=target_group_name)
        user.groups.add(group)
