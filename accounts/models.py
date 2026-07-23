from typing import ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext


class User(AbstractUser):  # type: ignore[django-manager-missing]
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
    api_token = models.UUIDField(null=True, blank=True, unique=True, db_index=True)
    birth_date = models.DateField(null=True, blank=True)
    # Default team/city for race registrations, so the registrant doesn't retype them each time.
    team = models.CharField(max_length=100, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    # Strava profile link, prefilled into the registration "additional info" field when a
    # competition collects Strava links (used later to match riders to their segment efforts).
    # Capped at the additional_info field's length so the prefilled value always fits.
    strava_link = models.URLField(max_length=100, blank=True, default="")
    # Saved calendar-filter preferences: exactly the same three filter dimensions the calendar uses,
    # so an opened calendar/list/map defaults to what this user cares about (issue #229). Left empty
    # for everyone by default -- the user opts in from their profile; the free-text ``city`` above is
    # unrelated and untouched. Directions are DisciplineCategory, disciplines their children.
    preferred_directions = models.ManyToManyField(
        "calendar_app.DisciplineCategory", blank=True, related_name="preferring_users"
    )
    preferred_disciplines = models.ManyToManyField(
        "calendar_app.Discipline", blank=True, related_name="preferring_users"
    )
    preferred_locations = models.ManyToManyField("locations.Location", blank=True, related_name="preferring_users")
    # Timestamp of the last rate-limited outgoing mail action (confirmation email at
    # signup/resend and the contact-owners message). Shared cooldown across all of them.
    last_mail_action_at = models.DateTimeField(null=True, blank=True)

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

    @property
    def public_display_name(self) -> str:
        """A name safe to show on public pages: the full name, or a neutral label.

        Falls back to a generic label (never the email, which is usually the login and PII) so
        leaving a comment on a public page can't expose the author's address.
        """
        return self.get_full_name() or gettext("Participant")

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

    def save(self, *args, **kwargs) -> None:
        if self.role == self.Role.OWNER:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    def can_manage_user(self, target_user: "User") -> bool:
        if self.is_superuser:
            return True
        editor_rank = self.get_role_rank()
        if editor_rank <= self.ROLE_HIERARCHY.index(self.Role.PARTICIPANT):
            return False
        return editor_rank >= target_user.get_role_rank()
