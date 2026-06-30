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


class StartListUpload(models.Model):
    """Start-list state pushed from a StartProtocolMaker instance, keyed by ``device_id``.

    Several referees register competitors on different machines; each pushes its own list under
    its own ``device_id`` (re-posting the same ``device_id`` overwrites it). FinishProtocolGenerator
    fetches every device's list for a competition and merges them into one start protocol.

    ``items`` are the raw ``#``-delimited competitor lines, stored opaquely (the site neither
    parses nor renders them).
    """

    objects: ClassVar[models.Manager[StartListUpload]]

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="start_list_uploads",
    )
    device_id = models.CharField(max_length=64)
    items = models.JSONField(default=list)
    # Strictly-increasing per-device revision supplied by the client; the upload endpoint rejects a
    # snapshot whose revision is older than (or conflicts at) the stored one, so a delayed/reordered
    # request can't roll the device's list back. The API requires a positive value; the column
    # default 0 only applies to rows created before this field existed.
    client_revision = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together: ClassVar[list] = [("competition", "device_id")]
        ordering: ClassVar[list] = ["device_id"]

    def __str__(self) -> str:
        return f"{self.competition} - {self.device_id} ({len(self.items)} items)"


class _TimingUploadBase(models.Model):
    """Shared base for the per-device timing streams pushed from WindowsChronometer.

    Mirrors :class:`StartListUpload`: each chronometer machine pushes its own snapshot under its
    own ``device_id`` (re-posting the same ``device_id`` overwrites it via a compare-and-set on
    ``client_revision``); FinishProtocolGenerator fetches every device's stream and merges them.
    ``items`` are the raw ``#``-delimited lines, stored opaquely (the site neither parses nor
    renders them).
    """

    device_id = models.CharField(max_length=64)
    items = models.JSONField(default=list)
    # Strictly-increasing per-device revision; the upload endpoint rejects a snapshot whose revision
    # is older than (or conflicts at) the stored one, so a delayed/reordered request can't roll the
    # device's data back. The API requires a positive value.
    client_revision = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class GroupTimesUpload(_TimingUploadBase):
    """Group-start times (``group#time#`` lines) pushed per ``device_id``."""

    objects: ClassVar[models.Manager[GroupTimesUpload]]

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="group_times_uploads",
    )

    class Meta(_TimingUploadBase.Meta):
        unique_together: ClassVar[list] = [("competition", "device_id")]
        ordering: ClassVar[list] = ["device_id"]

    def __str__(self) -> str:
        return f"{self.competition} - group - {self.device_id} ({len(self.items)} items)"


class FinishTimesUpload(_TimingUploadBase):
    """Finish-line crossings (point 0) (``number#time#action#`` lines) pushed per ``device_id``."""

    objects: ClassVar[models.Manager[FinishTimesUpload]]

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="finish_times_uploads",
    )

    class Meta(_TimingUploadBase.Meta):
        unique_together: ClassVar[list] = [("competition", "device_id")]
        ordering: ClassVar[list] = ["device_id"]

    def __str__(self) -> str:
        return f"{self.competition} - finish - {self.device_id} ({len(self.items)} items)"


class RemotePointUpload(_TimingUploadBase):
    """Remote (intermediate) control-point crossings, keyed by ``device_id`` and ``point_number``.

    Point numbers are 1..N (point 0 is the finish, handled by :class:`FinishTimesUpload`). Several
    machines may time the same point; the generator merges every device's lines for a given
    ``point_number`` into one control-point stream.
    """

    objects: ClassVar[models.Manager[RemotePointUpload]]

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="remote_point_uploads",
    )
    point_number = models.PositiveIntegerField()

    class Meta(_TimingUploadBase.Meta):
        unique_together: ClassVar[list] = [("competition", "device_id", "point_number")]
        ordering: ClassVar[list] = ["point_number", "device_id"]

    def __str__(self) -> str:
        return f"{self.competition} - point {self.point_number} - {self.device_id} ({len(self.items)} items)"
