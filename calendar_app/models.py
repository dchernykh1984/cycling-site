import datetime
import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone
from wagtail.search import index


class EventType(models.Model):
    objects: ClassVar[models.Manager["EventType"]]
    name = models.CharField(max_length=100)

    class Meta:
        ordering: ClassVar[list] = ["name"]
        verbose_name = "Event type"
        verbose_name_plural = "Event types"

    def __str__(self) -> str:
        return self.name or f"EventType #{self.pk}"


class CyclingDiscipline(models.Model):
    objects: ClassVar[models.Manager["CyclingDiscipline"]]
    name = models.CharField(max_length=100)

    class Meta:
        ordering: ClassVar[list] = ["name"]
        verbose_name = "Cycling discipline"
        verbose_name_plural = "Cycling disciplines"

    def __str__(self) -> str:
        return self.name or f"Discipline #{self.pk}"


class Competition(index.Indexed, models.Model):
    objects: ClassVar[models.Manager["Competition"]]

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_type = models.ForeignKey(
        "EventType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    discipline = models.ForeignKey(
        "CyclingDiscipline",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="competitions",
    )
    date_start = models.DateField()
    date_end = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        db_index=True,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    url_route = models.URLField(blank=True)
    url_announcement = models.URLField(blank=True)
    url_registration = models.URLField(blank=True)
    url_regulations = models.URLField(blank=True)
    url_results = models.URLField(blank=True)
    upload_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # --- Registration feature ---
    registration_enabled = models.BooleanField(default=False)

    class RegistrationMode(models.TextChoices):
        SELF_ONLY = "self_only", "Self only (linked to user account)"
        FREE = "free", "Free (can register any person)"

    registration_mode = models.CharField(
        max_length=20,
        choices=RegistrationMode.choices,
        default=RegistrationMode.SELF_ONLY,
        blank=True,
    )

    class BirthDateMode(models.TextChoices):
        YEAR = "year", "Year of birth"
        DATE = "date", "Full birth date"

    birth_date_mode = models.CharField(
        max_length=10,
        choices=BirthDateMode.choices,
        default=BirthDateMode.YEAR,
        blank=True,
    )

    require_approval = models.BooleanField(default=False)
    require_payment = models.BooleanField(default=False)
    allow_multiple_registrations = models.BooleanField(default=False)
    registration_deadline = models.DateField(null=True, blank=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)

    show_unapproved_in_list = models.BooleanField(default=False)
    show_unpaid_in_list = models.BooleanField(default=False)
    show_approval_status_col = models.BooleanField(default=False)
    show_payment_status_col = models.BooleanField(default=False)
    show_additional_info_field = models.BooleanField(default=True)

    # Permanent lock: True once registration is first activated; never reset to False.
    registration_mode_locked = models.BooleanField(default=False)

    search_fields: ClassVar[list] = [
        index.SearchField("title_ru"),
        index.SearchField("title_kk"),
        index.SearchField("title_en"),
        index.SearchField("description_ru"),
        index.SearchField("description_kk"),
        index.SearchField("description_en"),
        index.FilterField("status"),
    ]

    class Meta:
        ordering: ClassVar[list] = ["date_start"]
        verbose_name = "Competition"
        verbose_name_plural = "Competitions"

    def __str__(self) -> str:
        return self.title or f"Competition #{self.pk}"

    def get_calendar_end(self) -> str | None:
        if self.date_end:
            return (self.date_end + datetime.timedelta(days=1)).isoformat()
        return None

    def approve(self, reviewer) -> None:
        if self.status not in (self.Status.PENDING_APPROVAL, self.Status.DRAFT):
            raise ValueError(f"Cannot approve: competition is already '{self.get_status_display()}'.")
        self.status = self.Status.APPROVED
        self.approved_by = reviewer
        self.approved_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "approved_by", "approved_at", "rejection_reason"])

    def reject(self, reviewer, reason: str = "") -> None:
        if self.status not in (self.Status.PENDING_APPROVAL, self.Status.DRAFT):
            raise ValueError(f"Cannot reject: competition is already '{self.get_status_display()}'.")
        self.status = self.Status.REJECTED
        self.approved_by = reviewer
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "approved_by", "approved_at", "rejection_reason"])

    def is_registration_open(self) -> bool:
        if not self.registration_enabled:
            return False
        if self.status != self.Status.APPROVED:
            return False
        if self.registration_deadline and self.registration_deadline < datetime.date.today():
            return False
        return not self.is_limit_reached()

    def qualified_count(self, category=None) -> int:
        qs = self.registrations.filter(is_rejected=False)
        if category is not None:
            qs = qs.filter(category=category)
        if self.require_approval:
            qs = qs.filter(is_approved=True)
        if self.require_payment:
            qs = qs.filter(is_paid=True)
        return qs.count()

    def is_limit_reached(self, category=None) -> bool:
        if category is not None:
            if category.max_participants is None:
                return False
            return self.qualified_count(category=category) >= category.max_participants
        if self.max_participants is None:
            return False
        return self.qualified_count() >= self.max_participants
