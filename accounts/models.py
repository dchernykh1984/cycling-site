from typing import ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        GUEST = "guest", "Guest"
        PARTICIPANT = "participant", "Participant"
        ORGANIZER = "organizer", "Organizer"
        ADMIN = "admin", "Admin"
        OWNER = "owner", "Owner"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.GUEST,
        db_index=True,
    )

    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    theme = models.CharField(
        max_length=10,
        choices=[("light", "Light"), ("dark", "Dark")],
        default="light",
    )
    preferred_language = models.CharField(
        max_length=10,
        blank=True,
        default="",
        choices=[("", "Auto"), *settings.LANGUAGES],
    )

    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)

    ROLE_HIERARCHY: ClassVar[list[str]] = [
        Role.GUEST,
        Role.PARTICIPANT,
        Role.ORGANIZER,
        Role.ADMIN,
        Role.OWNER,
    ]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def get_role_rank(self) -> int:
        try:
            return self.ROLE_HIERARCHY.index(self.role)
        except ValueError:
            return 0

    def can_assign_role(self, target_role: str) -> bool:
        if target_role not in self.ROLE_HIERARCHY:
            return False
        if self.is_superuser:
            return True
        assigner_rank = self.get_role_rank()
        target_rank = self.ROLE_HIERARCHY.index(target_role)
        if assigner_rank <= self.ROLE_HIERARCHY.index(self.Role.PARTICIPANT):
            return False
        # participant is auto-assigned via email confirmation; manual assignment is admin+ only
        if target_role == self.Role.PARTICIPANT:
            return assigner_rank >= self.ROLE_HIERARCHY.index(self.Role.ADMIN)
        return assigner_rank >= target_rank

    def can_manage_user(self, target_user: "User") -> bool:
        # an editor may only touch users whose current rank does not exceed their own
        if self.is_superuser:
            return True
        editor_rank = self.get_role_rank()
        if editor_rank <= self.ROLE_HIERARCHY.index(self.Role.PARTICIPANT):
            return False
        return editor_rank >= target_user.get_role_rank()
