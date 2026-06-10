import datetime
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


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
        if gender == "M" and not self.male:
            return False
        if gender == "F" and not self.female:
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
    birth_date = models.DateField()
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
            return f"{self.participant_names.replace('<BR>', ', ')} - {self.competition}"
        return f"{self.last_name} {self.first_name} - {self.competition}"

    @property
    def is_relay(self) -> bool:
        return bool(self.participant_names)

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

    @property
    def is_qualified(self) -> bool:
        if self.is_rejected:
            return False
        comp = self.competition
        if comp.require_approval and not self.is_approved:
            return False
        if comp.require_payment and not self.is_paid:
            return False
        return True


def check_duplicate(competition, user, first_name: str, last_name: str, birth_date: datetime.date) -> bool:
    if competition.registration_mode == "self_only" and user:
        return CompetitionRegistration.objects.filter(competition=competition, user=user).exists()
    if competition.allow_multiple_registrations:
        return False
    return CompetitionRegistration.objects.filter(
        competition=competition,
        last_name__iexact=last_name,
        first_name__iexact=first_name,
        birth_date__year=birth_date.year,
    ).exists()
