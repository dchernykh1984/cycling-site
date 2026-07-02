import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.text import get_valid_filename
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from calendar_app.models import Competition
from protocols.models import Protocol, ProtocolVersion

router = Router(tags=["protocols"])

_MAX_VERSIONS = 10


def _competition_by_token(token: str) -> Competition:
    try:
        return Competition.objects.get(
            upload_token=token,
            status=Competition.Status.APPROVED,
            is_deleted=False,
        )
    except (Competition.DoesNotExist, ValidationError):
        raise HttpError(401, "Invalid competition_token") from None


class ProtocolUploadOut(Schema):
    id: int
    file_hash: str


class ProtocolDeleteOut(Schema):
    deleted: bool


@router.post(
    "/upload/",
    response=ProtocolUploadOut,
    auth=None,
    summary="Upload protocol HTML file",
)
def upload_protocol(  # noqa: C901
    request,
    competition_token: str = Form(...),
    protocol_type: str = Form("absolute"),
    is_live: bool = Form(True),
    stage_label: str = Form(""),
    html_file: UploadedFile = File(...),  # noqa: B008
):
    """
    Upload an HTML protocol file for a competition.
    Uses `competition_token` (the competition's upload token) for authentication.
    Called by FinishProtocolGenerator.
    """
    competition = _competition_by_token(competition_token)

    if protocol_type not in ("absolute", "group"):
        raise HttpError(400, "protocol_type must be 'absolute' or 'group'")

    content_type = getattr(html_file, "content_type", "") or ""
    media_type = content_type.split(";")[0].strip()
    if media_type != "text/html":
        raise HttpError(400, "File must be text/html")

    raw_name = html_file.name or ""
    if not raw_name.lower().endswith((".html", ".htm")):
        raise HttpError(400, "File must have .html or .htm extension")

    max_mb = getattr(settings, "MAX_PROTOCOL_SIZE_MB", 5)
    if html_file.size is None or html_file.size > max_mb * 1024 * 1024:
        raise HttpError(400, f"File too large (max {max_mb} MB)")

    content = html_file.read()

    _c = content.lstrip()
    if _c.startswith(b"\xef\xbb\xbf"):
        _c = _c[3:]
    if not _c.lstrip()[:15].lower().startswith(b"<"):
        raise HttpError(400, "File does not appear to be valid HTML")

    file_hash = hashlib.sha256(content).hexdigest()
    filename = get_valid_filename(html_file.name or "protocol.html")
    if not filename.lower().endswith(".html"):
        filename = filename + ".html"

    protocol, _ = Protocol.objects.get_or_create(
        competition=competition,
        protocol_type=protocol_type,
    )

    if protocol.html_file:
        protocol.html_file.delete(save=False)

    protocol.is_live = is_live
    protocol.stage_label = stage_label
    protocol.file_hash = file_hash
    protocol.html_file.save(filename, ContentFile(content), save=False)
    protocol.save()

    version = ProtocolVersion(protocol=protocol, file_hash=file_hash)
    version.html_file.save(f"v_{filename}", ContentFile(content), save=True)

    old_ids = list(
        ProtocolVersion.objects.filter(protocol=protocol)
        .order_by("-saved_at")
        .values_list("pk", flat=True)[_MAX_VERSIONS:]
    )
    if old_ids:
        for old in ProtocolVersion.objects.filter(pk__in=old_ids):
            old.html_file.delete(save=False)
        ProtocolVersion.objects.filter(pk__in=old_ids).delete()

    return {"id": protocol.pk, "file_hash": file_hash}


@router.post(
    "/delete/",
    response=ProtocolDeleteOut,
    auth=None,
    summary="Delete a protocol (removes its live-broadcast link from the competition page)",
)
def delete_protocol(
    request,
    competition_token: str = Form(...),
    protocol_type: str = Form("absolute"),
):
    """Delete a competition's protocol of the given type, if present.

    Idempotent: returns ``deleted=False`` (200) when there is nothing to delete. Called by
    FinishProtocolGenerator to drop a protocol the organizer no longer publishes, so its results
    link disappears from the competition detail page.
    """
    competition = _competition_by_token(competition_token)
    if protocol_type not in ("absolute", "group"):
        raise HttpError(400, "protocol_type must be 'absolute' or 'group'")

    protocol = Protocol.objects.filter(competition=competition, protocol_type=protocol_type).first()
    if protocol is None:
        return {"deleted": False}

    # Remove the stored files (rows cascade), so nothing is orphaned on disk.
    for version in protocol.versions.all():
        if version.html_file:
            version.html_file.delete(save=False)
    if protocol.html_file:
        protocol.html_file.delete(save=False)
    protocol.delete()
    return {"deleted": True}
