from typing import ClassVar

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    ACTION_CREATED = "created"
    ACTION_UPDATED = "updated"
    ACTION_DELETED = "deleted"

    ACTION_CHOICES: ClassVar[list] = [
        (ACTION_CREATED, "Created"),
        (ACTION_UPDATED, "Updated"),
        (ACTION_DELETED, "Deleted"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=255)
    changes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-timestamp"]
        verbose_name = "Audit log entry"
        verbose_name_plural = "Audit log"

    def __str__(self) -> str:
        user_label = str(self.user) if self.user_id else "anonymous"
        return f"[{self.timestamp}] {user_label} {self.action} {self.object_type} #{self.object_id}"
