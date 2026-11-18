import hashlib
import logging
from datetime import datetime
from http import HTTPStatus

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponse
from django.utils.text import get_valid_filename
from django.utils.translation import override
from ninja import File, Form, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, competition_by_token
from api.schemas import LocalizedStr
from calendar_app.models import Competition
from calendar_app.visibility import can_manage_or_own
from protocols import access, sections
from protocols.document import DocumentError
from protocols.document import parse as parse_document
from protocols.forms import SectionNamesForm
from protocols.models import Protocol, ProtocolSection, ProtocolVersion
from protocols.views import content_security_policy, protocol_state

router = Router(tags=["protocols"])
logger = logging.getLogger(__name__)
auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()

_MAX_VERSIONS = 10


class ProtocolUploadOut(Schema):
    id: int
    file_hash: str
    shown: str
    document_error: str | None = None


class ProtocolDeleteOut(Schema):
    deleted: bool


class SectionIn(Schema):
    name: LocalizedStr


class SectionOut(Schema):
    number: int
    name: LocalizedStr
    protocols: int


class ProtocolOut(Schema):
    id: int
    competition_id: int
    section: int
    # The section's name in every language, as the event's page heads its block.
    section_name: LocalizedStr
    protocol_type: str
    stage_label: str
    is_live: bool
    last_updated: datetime
    file_hash: str
    # "document" when the last upload carried a structured document, which the site draws; else "html".
    shown: str
    has_html: bool


class ProtocolVersionOut(Schema):
    saved_at: datetime
    file_hash: str


class ProtocolDetailOut(ProtocolOut):
    # The structured document as the site keeps it -- the fields of protocols/schema/protocol-document-v1.json,
    # defaults filled in, what the site does not know left out; null when the last upload brought none it took.
    document: dict | None = None
    # The update history the protocol's page lists, the latest first.
    versions: list[ProtocolVersionOut]


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
        raise HttpError(HTTPStatus.BAD_REQUEST, "File must be text/html")

    raw_name = html_file.name or ""
    if not raw_name.lower().endswith((".html", ".htm")):
        raise HttpError(HTTPStatus.BAD_REQUEST, "File must have .html or .htm extension")

    max_mb = settings.MAX_PROTOCOL_SIZE_MB
    if html_file.size is None or html_file.size > max_mb * 1024 * 1024:
        raise HttpError(HTTPStatus.BAD_REQUEST, f"File too large (max {max_mb} MB)")

    content = html_file.read()

    _c = content.lstrip()
    if _c.startswith(b"\xef\xbb\xbf"):
        _c = _c[3:]
    if not _c.lstrip()[:15].lower().startswith(b"<"):
        raise HttpError(HTTPStatus.BAD_REQUEST, "File does not appear to be valid HTML")

    filename = get_valid_filename(html_file.name or "protocol.html")
    if not filename.lower().endswith(".html"):
        filename = filename + ".html"
    return content, filename


def _replace_protocol(
    competition: Competition, protocol_type: str, section: int, fields: dict, html: tuple[bytes, str] | None
):
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
            # Checked under the event's lock, which deleting a section takes too.
            _check_section_exists(competition, section)
            protocol = (
                Protocol.objects.select_for_update()
                .filter(competition=competition, section=section, protocol_type=protocol_type)
                .first()
            ) or Protocol(competition=competition, section=section, protocol_type=protocol_type)
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
    max_mb = settings.MAX_PROTOCOL_SIZE_MB
    if document.size is None or document.size > max_mb * 1024 * 1024:
        raise DocumentError(f"The document is too large (max {max_mb} MB)")
    raw = document.read()
    return parse_document(raw), raw


def _content_hash(html: bytes | None, document: bytes | None) -> str:
    # An HTML-only upload keeps the hash it always had: the file's own.
    if document is None:
        return hashlib.sha256(html or b"").hexdigest()
    return hashlib.sha256(b"html\0" + (html or b"") + b"\0document\0" + document).hexdigest()


def _check_protocol_type(protocol_type: str) -> None:
    if protocol_type not in Protocol.ProtocolType.values:
        allowed = " or ".join(f"'{value}'" for value in Protocol.ProtocolType.values)
        raise HttpError(HTTPStatus.BAD_REQUEST, f"protocol_type must be {allowed}")


def _check_section(section: int) -> None:
    if not sections.FIRST <= section <= sections.LAST:
        raise HttpError(HTTPStatus.BAD_REQUEST, f"section must be a section's number, {sections.FIRST} or more")


def _check_section_exists(competition: Competition, section: int) -> None:
    if not sections.exists(competition, section):
        raise HttpError(
            HTTPStatus.BAD_REQUEST,
            f"The event has no protocol section {section}: add it on the event's page first",
        )


@router.post(
    "/upload/",
    response=ProtocolUploadOut,
    auth=None,
    summary="Upload a protocol: its HTML file, its structured document, or both from one run",
)
def upload_protocol(
    request,
    competition_token: str = Form(...),
    protocol_type: str = Form(Protocol.ProtocolType.ABSOLUTE),
    is_live: bool = Form(True),
    stage_label: str = Form(""),
    section: int = Form(sections.FIRST),
    html_file: UploadedFile | None = File(None),  # noqa: B008
    document: UploadedFile | None = File(None),  # noqa: B008
):
    """
    Upload a competition's protocol, authenticated by `competition_token` (the event's upload token).

    `html_file` is the HTML the timing software wrote; `document` is the structured protocol
    (protocols/document.py, JSON Schema in protocols/schema/). `section` is the number of the event's
    protocol section to publish into: the first, every event's own, unless the organizer added another
    on the event's page; an event holds one protocol of each type per section. The upload replaces
    whatever the protocol held: a document is drawn by the site, HTML alone is shown as it is. Sent together they
    are one run -- the document is shown and the HTML kept as the original. When a document comes
    with HTML but cannot be accepted, the HTML is stored and `document_error` says why.
    Called by FinishProtocolGenerator and StravaProtocolGenerator.
    """
    competition = competition_by_token(competition_token)

    _check_protocol_type(protocol_type)
    _check_section(section)
    if html_file is None and document is None:
        raise HttpError(HTTPStatus.BAD_REQUEST, "Send html_file, document or both")

    html = _read_html(html_file) if html_file is not None else None
    parsed = raw_document = None
    document_error = None
    if document is not None:
        try:
            parsed, raw_document = _read_document(document)
        except DocumentError as exc:
            if html is None:
                raise HttpError(HTTPStatus.BAD_REQUEST, str(exc)) from None
            document_error = str(exc)

    file_hash = _content_hash(html[0] if html else None, raw_document)
    protocol = _replace_protocol(
        competition,
        protocol_type,
        section,
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
    protocol_type: str = Form(Protocol.ProtocolType.ABSOLUTE),
    section: int = Form(sections.FIRST),
):
    """Delete a competition's protocol of the given type in the given section (the first by default).

    Idempotent: returns ``deleted=False`` (200) when there is nothing to delete; a section the event
    does not have is a 400. Called by the protocol generators to drop a protocol the organizer no
    longer publishes, so its results link disappears from the competition detail page.
    """
    competition = competition_by_token(competition_token)
    _check_protocol_type(protocol_type)
    _check_section(section)

    with transaction.atomic():
        Competition.objects.select_for_update().get(pk=competition.pk)
        _check_section_exists(competition, section)
        protocol = (
            Protocol.objects.select_for_update()
            .filter(competition=competition, section=section, protocol_type=protocol_type)
            .first()
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


# -- Reading: what the protocol pages show, under their rule (protocols/access.py) --------------------


def _readable(request, protocol_id: int) -> Protocol:
    protocol = access.readable_protocol(request.auth, protocol_id)
    if protocol is None:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return protocol


def _section_names(competition: Competition) -> dict[int, dict[str, str]]:
    return {row["number"]: row["names"] for row in sections.listing(competition)}


def _protocol_out(protocol: Protocol, names: dict[int, dict[str, str]]) -> dict:
    return {
        "id": protocol.pk,
        "competition_id": protocol.competition_id,
        "section": protocol.section,
        "section_name": names.get(protocol.section) or sections.names(None),
        "protocol_type": protocol.protocol_type,
        "stage_label": protocol.stage_label,
        "is_live": protocol.is_live,
        "last_updated": protocol.last_updated,
        "file_hash": protocol.file_hash,
        "shown": protocol_state(protocol)["shown"],
        "has_html": bool(protocol.html_file),
    }


@router.get(
    "/",
    response=list[ProtocolOut],
    auth=optional_auth,
    summary="List an event's protocols, in the order of its sections (whoever may read its protocol pages)",
)
def list_protocols(request, competition_id: int):
    """An event's protocols as its page links them. A published event's are anybody's; an invite-only
    event's only its managers' and the people it lets in, by their token; a hidden, unpublished or
    deleted event answers 404, as one that does not exist does."""
    competition = Competition.objects.filter(pk=competition_id).first()
    if competition is None or not access.shows_protocols(request.auth, competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    names = _section_names(competition)
    return [_protocol_out(protocol, names) for protocol in competition.protocols.order_by("section", "pk")]


@router.get(
    "/{protocol_id}",
    response=ProtocolDetailOut,
    auth=optional_auth,
    summary="A protocol: its structured document and its update history",
)
def get_protocol(request, protocol_id: int):
    """The protocol with the document the site draws -- null when the last upload brought none it took,
    HTML alone or with a document it refused -- and the times of its last uploads, as its page lists them;
    its HTML file is at ``/{protocol_id}/html``."""
    protocol = _readable(request, protocol_id)
    return {
        **_protocol_out(protocol, _section_names(protocol.competition)),
        "document": protocol.document,
        "versions": list(
            protocol.versions.order_by("-saved_at", "-pk").values("saved_at", "file_hash")[:_MAX_VERSIONS]
        ),
    }


@router.get(
    "/{protocol_id}/html", auth=optional_auth, summary="A protocol's HTML file, as the timing software wrote it"
)
def get_protocol_html(request, protocol_id: int):
    """The file as uploaded, as an attachment, under the policy the protocol's page frames it with: it is
    somebody else's markup on this site's address, so it may run nothing that reaches outside or this site."""
    protocol = _readable(request, protocol_id)
    if not protocol.html_file:
        raise HttpError(HTTPStatus.NOT_FOUND, "The protocol has no HTML file")
    try:
        with protocol.html_file.open("rb") as stored:
            content = stored.read()
    except OSError:
        raise HttpError(HTTPStatus.NOT_FOUND, "The protocol has no HTML file") from None
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = content_security_policy(request)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = f'attachment; filename="protocol-{protocol.pk}.html"'
    response["Cache-Control"] = "no-store"
    return response


# -- Sections (issue #452): what the organizer does on the event's page of its protocol sections -----


def _managed_event(user, competition_id: int) -> Competition:
    competition = Competition.objects.filter(pk=competition_id, is_deleted=False).first()
    if competition is None or not can_manage_or_own(user, competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return competition


def _section(competition: Competition, number: int) -> dict:
    """The section as the API shows it, or a 404 for a number the event does not have."""
    for row in sections.listing(competition):
        if row["number"] == number:
            return {"number": number, "name": row["names"], "protocols": row["protocols"]}
    raise HttpError(HTTPStatus.NOT_FOUND, "Not found")


def _names(given: dict[str, str]) -> dict[str, str]:
    form = SectionNamesForm(given)
    if not form.is_valid():
        raise HttpError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "; ".join(f"name.{field}: {' '.join(str(e) for e in errors)}" for field, errors in form.errors.items()),
        )
    return form.names()


@router.get(
    "/competitions/{competition_id}/sections",
    response=list[SectionOut],
    auth=auth,
    summary="List an event's protocol sections (its author and managers)",
)
def list_sections(request, competition_id: int):
    competition = _managed_event(request.auth, competition_id)
    return [
        {"number": row["number"], "name": row["names"], "protocols": row["protocols"]}
        for row in sections.listing(competition)
    ]


@router.post(
    "/competitions/{competition_id}/sections",
    response={HTTPStatus.CREATED: SectionOut},
    auth=auth,
    summary="Add a protocol section, named in every language",
)
def add_section(request, competition_id: int, payload: SectionIn):
    """The new section gets a number the event never had; the timing software publishes into it by that number."""
    competition = _managed_event(request.auth, competition_id)
    number = sections.add(competition, _names(payload.name.dict())).number
    return Status(HTTPStatus.CREATED, _section(competition, number))


@router.patch(
    "/competitions/{competition_id}/sections/{number}",
    response=SectionOut,
    auth=auth,
    summary="Rename a protocol section; a language left empty keeps its name",
)
def rename_section(request, competition_id: int, number: int, payload: SectionIn):
    competition = _managed_event(request.auth, competition_id)
    current = _section(competition, number)["name"]
    given = {code: value or current[code] for code, value in payload.name.dict().items()}
    try:
        sections.rename(competition, number, _names(given))
    except ProtocolSection.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found") from None
    return _section(competition, number)


@router.delete(
    "/competitions/{competition_id}/sections/{number}",
    response={HTTPStatus.NO_CONTENT: None},
    auth=auth,
    summary="Delete a protocol section that holds no protocols",
)
def delete_section(request, competition_id: int, number: int):
    """The first section stays, and one with protocols stays until the generator deletes them (409)."""
    competition = _managed_event(request.auth, competition_id)
    _section(competition, number)
    try:
        sections.delete(competition, number)
    except ProtocolSection.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found") from None
    except sections.SectionRefusedError as exc:
        with override("en"):
            raise HttpError(HTTPStatus.CONFLICT, str(exc)) from None
    return Status(HTTPStatus.NO_CONTENT, None)
