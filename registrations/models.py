import datetime
import html
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from accounts.models import FIRST_BIRTH_YEAR, User, validate_birth_date

# How a relay team's names, birth years and cities are joined in one column; the timing tools read it so.
RELAY_SEPARATOR = "<BR>"
# The birth date stored when the form gave none: the earliest year the site takes.
UNKNOWN_BIRTH_DATE = datetime.date(FIRST_BIRTH_YEAR, 1, 1)


class Team(models.Model):
    name = models.CharField(max_length=100)
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list] = [models.UniqueConstraint(Lower("name"), name="team_name_unique_ci")]
        verbose_name = "Team"
        verbose_name_plural = "Teams"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_or_restore(cls, name: str) -> "Team":
        existing = cls.objects.filter(name__iexact=name).first()
        if existing:
            if existing.is_deleted:
                existing.is_deleted = False
                existing.save(update_fields=["is_deleted"])
            return existing
        return cls.objects.create(name=name)


class RegistrationCategory(models.Model):
    competition = models.ForeignKey(
        "calendar_app.Competition",
        on_delete=models.CASCADE,
        related_name="registration_categories",
    )
    name = models.CharField(max_length=100)
    male = models.BooleanField(default=True)
    female = models.BooleanField(default=True)
    birth_from = models.DateField(null=True, blank=True)
    birth_to = models.DateField(null=True, blank=True)
    laps = models.PositiveIntegerField(null=True, blank=True)
    bib_from = models.PositiveIntegerField(null=True, blank=True)
    bib_to = models.PositiveIntegerField(null=True, blank=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list[str]] = ["order", "pk"]

    def __str__(self) -> str:
        return f"{self.competition} - {self.name}"

    def matches_gender(self, gender: str) -> bool:
        if gender == User.Gender.MALE and not self.male:
            return False
        if gender == User.Gender.FEMALE and not self.female:
            return False
        return True

    def matches(self, gender: str, birth_date: datetime.date) -> bool:
        if not self.matches_gender(gender):
            return False
        if self.birth_from and birth_date < self.birth_from:
            return False
        if self.birth_to and birth_date > self.birth_to:
            return False
        return True

    def is_open(self) -> bool:
        if self.is_deleted:
            return False
        return not self.competition.is_limit_reached(category=self)


class CompetitionRegistration(models.Model):
    competition = models.ForeignKey(
        "calendar_app.Competition",
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="competition_registrations",
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    participant_names = models.TextField(blank=True, default="")
    participant_birth_years = models.TextField(blank=True, default="")
    participant_cities = models.TextField(blank=True, default="")
    birth_date = models.DateField(validators=[validate_birth_date])
    gender = models.CharField(max_length=1, choices=[("M", "Male"), ("F", "Female")])
    category = models.ForeignKey(
        RegistrationCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registrations",
    )
    city = models.CharField(max_length=100, blank=True)
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registrations",
    )
    additional_info = models.CharField(max_length=100, blank=True)
    is_approved = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    rejection_note = models.CharField(max_length=500, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["registered_at"]

    def __str__(self) -> str:
        if self.participant_names:
            return f"{self.participant_names.replace(RELAY_SEPARATOR, ', ')} - {self.competition}"
        return f"{self.last_name} {self.first_name} - {self.competition}"

    @property
    def is_relay(self) -> bool:
        return bool(self.participant_names)

    @property
    def display_name(self) -> str:
        """Who the entry is for, as plain text: a relay team's members, or one person's name."""
        if self.participant_names:
            # Stored escaped and joined with RELAY_SEPARATOR, for the participant list's |safe.
            return html.unescape(self.participant_names.replace(RELAY_SEPARATOR, ", "))
        return f"{self.last_name} {self.first_name}"

    def clean(self) -> None:
        if self.pk:
            return
        if self.participant_names:
            return
        if not (self.competition_id and self.first_name and self.last_name and self.birth_date):
            return
        if check_duplicate(self.competition, self.user, self.first_name, self.last_name, self.birth_date):
            raise ValidationError("A duplicate registration already exists.")

    @property
    def birth_year(self) -> int:
        return self.birth_date.year


def counts(entry, competition) -> bool:
    """Whether an entry counts -- toward the limit, for a start number, in the lists the timing tools
    read: not rejected, and approved and paid where the event asks for it.

    So a rider's number is their place among the actual field, the same in the public and the
    manager's view, and a rejected row never shifts anyone. ``counted`` and ``counted_q`` ask the same
    of the database.
    """
    if entry.is_rejected:
        return False
    if competition.require_approval and not entry.is_approved:
        return False
    return not (competition.require_payment and not entry.is_paid)


def counted(competition, *, paid_only: bool = True):
    """The entries of ``competition`` that count; ``paid_only=False`` keeps the unpaid ones, for a
    referee who asks to see what is still outstanding."""
    entries = competition.registrations.filter(is_rejected=False)
    if competition.require_approval:
        entries = entries.filter(is_approved=True)
    if competition.require_payment and paid_only:
        entries = entries.filter(is_paid=True)
    return entries


def counted_q() -> Q:
    """``counts`` as a condition over the entries of many events at once."""
    return (
        Q(is_rejected=False)
        & ~Q(competition__require_approval=True, is_approved=False)
        & ~Q(competition__require_payment=True, is_paid=False)
    )


def check_duplicate(competition, user, first_name: str, last_name: str, birth_date: datetime.date) -> bool:
    if competition.registration_mode == competition.RegistrationMode.SELF_ONLY and user:
        return CompetitionRegistration.objects.filter(competition=competition, user=user).exists()
    if competition.allow_multiple_registrations:
        return False
    return CompetitionRegistration.objects.filter(
        competition=competition,
        last_name__iexact=last_name,
        first_name__iexact=first_name,
        birth_date__year=birth_date.year,
    ).exists()
