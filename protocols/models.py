from __future__ import annotations

from typing import ClassVar

from django.db import models

from calendar_app.models import Competition


class Protocol(models.Model):
    objects: ClassVar[models.Manager[Protocol]]

    class ProtocolType(models.TextChoices):
        ABSOLUTE = "absolute", "Absolute"
        GROUP = "group", "Group"

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="protocols",
    )
    protocol_type = models.CharField(max_length=20, choices=ProtocolType.choices)
    html_file = models.FileField(upload_to="protocols/")
    last_updated = models.DateTimeField(auto_now=True)
    is_live = models.BooleanField(default=True)
    stage_label = models.CharField(max_length=200, blank=True)
    file_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together: ClassVar[list] = [("competition", "protocol_type")]

    def __str__(self) -> str:
        return f"{self.competition} - {self.protocol_type}"


class ProtocolVersion(models.Model):
    objects: ClassVar[models.Manager[ProtocolVersion]]

    protocol = models.ForeignKey(
        Protocol,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    html_file = models.FileField(upload_to="protocol_versions/")
    saved_at = models.DateTimeField(auto_now_add=True)
    file_hash = models.CharField(max_length=64)

    class Meta:
        ordering: ClassVar[list] = ["-saved_at"]

    def __str__(self) -> str:
        return f"v{self.pk} of {self.protocol_id}"
