import hashlib
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.text import get_valid_filename
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from api.auth import competition_by_token
from calendar_app.models import Competition
from protocols.document import DocumentError
from protocols.document import parse as parse_document
from protocols.models import Protocol, ProtocolVersion

router = Router(tags=["protocols"])
logger = logging.getLogger(__name__)

_MAX_VERSIONS = 10


class ProtocolUploadOut(Schema):
    id: int
    file_hash: str
    shown: str
    document_error: str | None = None


class ProtocolDeleteOut(Schema):
    deleted: bool


def _delete_files(names: list) -> None:
    for name in filter(None, names):
        try:
            default_storage.delete(name)
        except OSError:
            logger.warning("Could not delete the displaced protocol file %s", name, exc_info=True)


def _read_html(html_file: UploadedFile) -> tuple[bytes, str]:
    """The uploaded HTML and the name to store it under, or a 400 saying what is wrong with it."""
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

    filename = get_valid_filename(html_file.name or "protocol.html")
    if not filename.lower().endswith(".html"):
        filename = filename + ".html"
    return content, filename


def _replace_protocol(competition: Competition, protocol_type: str, fields: dict, html: tuple[bytes, str] | None):
    """Switch a protocol to one upload's content, all of it or nothing.

    The new files are written under names of their own before anything else changes; the protocol,
    its new version and the pruning of old versions then switch in one transaction, uploads of one
    event taking turns on the event's row; the files they displace are deleted only once that
    transaction has committed. Whatever fails on the way, the protocol keeps its previous content
    and its file, and the new files are removed again.
    """
    saved: list[str] = []
    try:
        main_name = version_name = ""
        if html is not None:
            content, filename = html
            main_name = default_storage.save(f"protocols/{filename}", ContentFile(content))
            saved.append(main_name)
            version_name = default_storage.save(f"protocol_versions/v_{filename}", ContentFile(content))
            saved.append(version_name)
        with transaction.atomic():
            Competition.objects.select_for_update().get(pk=competition.pk)
            protocol = (
                Protocol.objects.select_for_update()
                .filter(competition=competition, protocol_type=protocol_type)
                .first()
            ) or Protocol(competition=competition, protocol_type=protocol_type)
            displaced = [protocol.html_file.name] if protocol.html_file else []
            protocol.html_file = main_name
            for field, value in fields.items():
                setattr(protocol, field, value)
            protocol.save()
            ProtocolVersion.objects.create(
                protocol=protocol,
                file_hash=protocol.file_hash,
                html_file=version_name,
                document=protocol.document,
            )
            old = list(ProtocolVersion.objects.filter(protocol=protocol).order_by("-saved_at", "-pk")[_MAX_VERSIONS:])
            displaced += [v.html_file.name for v in old if v.html_file]
            ProtocolVersion.objects.filter(pk__in=[v.pk for v in old]).delete()
            transaction.on_commit(lambda: _delete_files(displaced))
    except BaseException:
        _delete_files(saved)
        raise
    return protocol


def _read_document(document: UploadedFile) -> tuple[dict, bytes]:
    """The accepted document and its bytes, or DocumentError saying what is wrong with it."""
    content_type = getattr(document, "content_type", "") or ""
    if content_type.split(";")[0].strip() != "application/json":
        raise DocumentError("The document must be application/json")
    if not (document.name or "").lower().endswith(".json"):
        raise DocumentError("The document must have a .json extension")
    max_mb = getattr(settings, "MAX_PROTOCOL_SIZE_MB", 5)
    if document.size is None or document.size > max_mb * 1024 * 1024:
        raise DocumentError(f"The document is too large (max {max_mb} MB)")
    raw = document.read()
    return parse_document(raw), raw


def _content_hash(html: bytes | None, document: bytes | None) -> str:
    # An HTML-only upload keeps the hash it always had: the file's own.
    if document is None:
        return hashlib.sha256(html or b"").hexdigest()
    return hashlib.sha256(b"html\0" + (html or b"") + b"\0document\0" + document).hexdigest()


@router.post(
    "/upload/",
    response=ProtocolUploadOut,
    auth=None,
    summary="Upload a protocol: its HTML file, its structured document, or both from one run",
)
def upload_protocol(
    request,
    competition_token: str = Form(...),
    protocol_type: str = Form("absolute"),
    is_live: bool = Form(True),
    stage_label: str = Form(""),
    html_file: UploadedFile | None = File(None),  # noqa: B008
    document: UploadedFile | None = File(None),  # noqa: B008
):
    """
    Upload a competition's protocol, authenticated by `competition_token` (the event's upload token).

    `html_file` is the HTML the timing software wrote; `document` is the structured protocol
    (protocols/document.py, JSON Schema in protocols/schema/). The upload replaces whatever the
    protocol held: a document is drawn by the site, HTML alone is shown as it is. Sent together they
    are one run -- the document is shown and the HTML kept as the original. When a document comes
    with HTML but cannot be accepted, the HTML is stored and `document_error` says why.
    Called by FinishProtocolGenerator and StravaProtocolGenerator.
    """
    competition = competition_by_token(competition_token)

    if protocol_type not in Protocol.ProtocolType.values:
        raise HttpError(400, "protocol_type must be 'absolute' or 'group'")
    if html_file is None and document is None:
        raise HttpError(400, "Send html_file, document or both")

    html = _read_html(html_file) if html_file is not None else None
    parsed = raw_document = None
    document_error = None
    if document is not None:
        try:
            parsed, raw_document = _read_document(document)
        except DocumentError as exc:
            if html is None:
                raise HttpError(400, str(exc)) from None
            document_error = str(exc)

    file_hash = _content_hash(html[0] if html else None, raw_document)
    protocol = _replace_protocol(
        competition,
        protocol_type,
        {"is_live": is_live, "stage_label": stage_label, "file_hash": file_hash, "document": parsed},
        html,
    )
    return {
        "id": protocol.pk,
        "file_hash": file_hash,
        "shown": "document" if parsed is not None else "html",
        "document_error": document_error,
    }


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
    competition = competition_by_token(competition_token)
    if protocol_type not in Protocol.ProtocolType.values:
        raise HttpError(400, "protocol_type must be 'absolute' or 'group'")

    with transaction.atomic():
        Competition.objects.select_for_update().get(pk=competition.pk)
        protocol = (
            Protocol.objects.select_for_update().filter(competition=competition, protocol_type=protocol_type).first()
        )
        if protocol is None:
            return {"deleted": False}
        # Remove the stored files (rows cascade) once the rows are gone, so nothing is orphaned on disk.
        files = [v.html_file.name for v in protocol.versions.all() if v.html_file]
        if protocol.html_file:
            files.append(protocol.html_file.name)
        protocol.delete()
        transaction.on_commit(lambda: _delete_files(files))
    return {"deleted": True}
