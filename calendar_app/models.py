import datetime
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
