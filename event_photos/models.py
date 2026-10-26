"""Photos of an event kept in an external folder and indexed by bib (issue #349).

The photos stay where the photographer put them (a Dropbox shared folder); the folder carries
``photo-index.v1.json``, which the site imports on request into the rows below. Participants' own
"this is me" / "not me" marks are site data, kept apart from the imported index so that no import
can erase them. Which registration got which bib comes from the start list StartProtocolMaker sends
(``IssuedBib``), never from names.
"""

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ExternalAlbum(models.Model):
    competition = models.ForeignKey(
        "calendar_app.Competition", on_delete=models.CASCADE, related_name="external_albums", verbose_name=_("Event")
    )
    folder_url = models.URLField(_("Folder link"), max_length=500)
    title = models.CharField(_("Title"), max_length=200)
    credit = models.CharField(_("Photographer"), max_length=200, blank=True)
    # The album's identity from its index; one folder per identity on the whole site, so a copied
    # example or somebody else's folder cannot take over an album already connected.
    album_uuid = models.UUIDField(null=True, blank=True, unique=True)
    revision = models.PositiveBigIntegerField(default=0)
    index_sha256 = models.CharField(max_length=64, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_error = models.TextField(blank=True)
    photo_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    inventory_complete = models.BooleanField(default=False)
    is_hidden = models.BooleanField(_("Hidden"), default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["created_at", "pk"]

    def __str__(self) -> str:
        return self.title


class IndexedPhoto(models.Model):
    album = models.ForeignKey(ExternalAlbum, on_delete=models.CASCADE, related_name="photos")
    photo_uuid = models.UUIDField()
    original_path = models.CharField(max_length=500)
    original_sha256 = models.CharField(max_length=64)
    original_bytes = models.PositiveBigIntegerField()
    original_view_url = models.URLField(max_length=500, blank=True)
    preview_path = models.CharField(max_length=500, blank=True)
    preview_sha256 = models.CharField(max_length=64, blank=True)
    processing_state = models.CharField(max_length=10)
    # False only after an explicit tombstone in a newer index; the row stays so marks survive.
    in_index = models.BooleanField(default=True)
    # The organizer's own hiding; an import never touches it.
    is_hidden = models.BooleanField(default=False)
    # The thumbnail the site keeps, and the digest it was made from (preview, else original).
    thumb_file = models.CharField(max_length=300, blank=True)
    thumb_source_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["album", "photo_uuid"], name="event_photo_unique_uuid")
        ]
        ordering: ClassVar[list[str]] = ["original_path", "pk"]

    def __str__(self) -> str:
        return self.original_path

    @property
    def source_sha256(self) -> str:
        return self.preview_sha256 or self.original_sha256

    @property
    def file_name(self) -> str:
        return self.original_path.rsplit("/", 1)[-1]


class BibObservation(models.Model):
    class State(models.TextChoices):
        CANDIDATE = "candidate"
        ACCEPTED = "accepted"
        REJECTED = "rejected"

    photo = models.ForeignKey(IndexedPhoto, on_delete=models.CASCADE, related_name="bibs")
    value = models.CharField(max_length=32, db_index=True)
    state = models.CharField(max_length=10, choices=State.choices)
    method = models.CharField(max_length=12)
    confidence = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.value} ({self.state})"


class IssuedBib(models.Model):
    """A bib the start list gave to a registration (from the trailing ``r<id>`` field)."""

    class State(models.TextChoices):
        ACTIVE = "active"
        CONFLICT = "conflict"
        REVIEW = "review"

    competition = models.ForeignKey("calendar_app.Competition", on_delete=models.CASCADE, related_name="issued_bibs")
    registration = models.ForeignKey(
        "registrations.CompetitionRegistration", on_delete=models.CASCADE, related_name="issued_bibs"
    )
    bib = models.CharField(max_length=32)
    state = models.CharField(max_length=10, choices=State.choices, default=State.ACTIVE)
    device_id = models.CharField(max_length=64, blank=True)
    client_revision = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["competition", "registration", "bib"], name="issued_bib_unique")
        ]

    def __str__(self) -> str:
        return f"{self.bib} -> r{self.registration_id}"


class IssuedBibEvent(models.Model):
    """Append-only history of bib assignments; the generic audit log keeps only field names."""

    competition = models.ForeignKey("calendar_app.Competition", on_delete=models.CASCADE, related_name="+")
    registration_id = models.BigIntegerField()
    bib = models.CharField(max_length=32)
    change = models.CharField(max_length=10)  # assigned / conflict / review / withdrawn
    device_id = models.CharField(max_length=64, blank=True)
    client_revision = models.PositiveBigIntegerField(default=0)
    at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.change} {self.bib} r{self.registration_id}"


class PhotoDecision(models.Model):
    class State(models.TextChoices):
        ME = "me"
        NOT_ME = "not_me"

    registration = models.ForeignKey(
        "registrations.CompetitionRegistration", on_delete=models.CASCADE, related_name="photo_decisions"
    )
    photo = models.ForeignKey(IndexedPhoto, on_delete=models.CASCADE, related_name="decisions")
    state = models.CharField(max_length=6, choices=State.choices)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["registration", "photo"], name="photo_decision_unique")
        ]

    def __str__(self) -> str:
        return f"{self.state or '-'} r{self.registration_id}"


class PhotoDecisionEvent(models.Model):
    """Every change of a decision, so an undo reverts exactly one of them."""

    decision = models.ForeignKey(PhotoDecision, on_delete=models.CASCADE, related_name="events")
    from_state = models.CharField(max_length=6, blank=True)
    to_state = models.CharField(max_length=6)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.from_state or '-'} -> {self.to_state}"
