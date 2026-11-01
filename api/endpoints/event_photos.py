"""Event photos over the API (issue #349): what the pages do, by the same rules (event_photos.permissions)
and the same actions. Anything the caller may not see answers 404."""

from http import HTTPStatus

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Schema, Status
from ninja.errors import HttpError
from pydantic import Field

from api.auth import ApiTokenAuth, OptionalApiTokenAuth
from api.schemas import LocalizedStr, localize_field
from calendar_app.models import Competition
from event_photos import actions
from event_photos.archive import ArchiveBusyError, ArchiveTooBigError
from event_photos.dropbox import open_url
from event_photos.forms import ExternalAlbumForm
from event_photos.models import ExternalAlbum, IndexedPhoto, PhotoDecision, StartListDiagnostics
from event_photos.permissions import can_manage_albums, can_mark, can_see_event, can_see_registration, looked_after
from event_photos.views import (
    archive_response,
    bib_archive_name,
    thumbnail_response,
    visible_albums,
)
from registrations.models import CompetitionRegistration

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()
router = Router(tags=["event-photos"])
PER_PAGE = 50


class AlbumOut(Schema):
    id: int
    competition_id: int
    title: LocalizedStr
    credit: LocalizedStr
    photo_count: int
    processed_count: int
    inventory_complete: bool
    revision: int
    is_hidden: bool
    # For the event's managers only (null for everybody else): how the last import went.
    import_state: str | None = None
    last_error: str | None = None

    @staticmethod
    def resolve_import_state(obj, context) -> str | None:
        if not can_manage_albums(context["request"].auth, obj.competition):
            return None
        if obj.last_error:
            return "failed"
        return "imported" if obj.imported_at else "not-imported"

    @staticmethod
    def resolve_last_error(obj, context) -> str | None:
        if not can_manage_albums(context["request"].auth, obj.competition):
            return None
        return obj.last_error

    @staticmethod
    def resolve_title(obj) -> LocalizedStr:
        return localize_field(obj, "title")

    @staticmethod
    def resolve_credit(obj) -> LocalizedStr:
        return localize_field(obj, "credit")


class PhotoOut(Schema):
    id: int
    album_id: int
    file_name: str
    # Empty when no thumbnail can be made (an original over 20 MB without a preview).
    thumbnail_url: str
    open_url: str
    is_hidden: bool
    confirmed: bool | None = None
    decision: str | None = None


class PhotoPageOut(Schema):
    count: int
    page: int
    photos: list[PhotoOut]


class RegistrationAlbumOut(Schema):
    registration_id: int
    competition_id: int
    competition_title: str
    bibs: list[str]
    count: int
    confirmed: int
    state: str
    cover_thumbnail_url: str
    participant: str
    category: LocalizedStr | None


class DecisionIn(Schema):
    state: str = Field(pattern="^(me|not_me)$")


class DecisionOut(Schema):
    state: str
    event_id: int | None


class UndoIn(Schema):
    event_id: int


class AlbumIn(Schema):
    folder_url: str
    title_ru: str = ""
    title_kk: str = ""
    title_en: str = ""
    credit_ru: str = ""
    credit_kk: str = ""
    credit_en: str = ""


class AlbumPatchIn(Schema):
    is_hidden: bool


class StatsOut(Schema):
    confirmed: int
    rejected: int
    unchecked: int
    by_method: list[dict]


def _competition(user, pk) -> Competition:
    competition = get_object_or_404(Competition, pk=pk)
    if not can_see_event(user, competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return competition


def _thumbnail_url(request, photo) -> str:
    if photo is None or photo.needs_preview:
        return ""
    return request.build_absolute_uri(f"/api/v1/event-photos/photos/{photo.pk}/thumbnail?v={photo.source_sha256[:16]}")


def _registration_card(request, registration) -> dict:
    summary = actions.registration_summary(registration)
    return {
        "registration_id": registration.pk,
        "competition_id": registration.competition_id,
        "competition_title": registration.competition.title,
        "bibs": summary["bibs"],
        "count": summary["count"],
        "confirmed": summary["confirmed"],
        "state": summary["state"],
        "cover_thumbnail_url": _thumbnail_url(request, summary["cover"]),
        "participant": registration.display_name.strip(),
        "category": localize_field(registration.category, "name") if registration.category else None,
    }


def _photos(request, qs, competition, page_number, decisions=None) -> dict:
    page = Paginator(qs, PER_PAGE).get_page(page_number)
    out = []
    for photo in page:
        out.append(
            {
                "id": photo.pk,
                "album_id": photo.album_id,
                "file_name": photo.file_name,
                "is_hidden": photo.is_hidden,
                # The API's own address, so the caller's token is what decides, as for the list.
                "thumbnail_url": _thumbnail_url(request, photo),
                "open_url": open_url(photo),
                "confirmed": getattr(photo, "confirmed", None),
                "decision": decisions.get(photo.pk) if decisions is not None else None,
            }
        )
    return {"count": page.paginator.count, "page": page.number, "photos": out}


@router.get("/photos/{photo_id}/thumbnail", auth=optional_auth, summary="A photo's thumbnail (JPEG)")
def photo_thumbnail(request, photo_id: int, v: str = ""):
    photo = get_object_or_404(IndexedPhoto.objects.select_related("album"), pk=photo_id)
    return thumbnail_response(request.auth, _competition(request.auth, photo.album.competition_id), photo.pk)


@router.get("/competitions/{competition_id}/albums", response=list[AlbumOut], auth=optional_auth)
def list_albums(request, competition_id: int):
    return list(visible_albums(request.auth, _competition(request.auth, competition_id)).select_related("competition"))


@router.get("/competitions/{competition_id}/photos", response=PhotoPageOut, auth=optional_auth)
def search_by_bib(request, competition_id: int, bib: str, page: int = 1):
    competition = _competition(request.auth, competition_id)
    albums = visible_albums(request.auth, competition)
    qs = actions.bib_photos(competition, bib[:32]).filter(album__in=albums).select_related("album")
    return _photos(request, qs, competition, page)


@router.get("/albums/{album_id}/photos", response=PhotoPageOut, auth=optional_auth)
def album_photos(request, album_id: int, page: int = 1):
    album = get_object_or_404(ExternalAlbum, pk=album_id)
    competition = _competition(request.auth, album.competition_id)
    if not visible_albums(request.auth, competition).filter(pk=album.pk).exists():
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    qs = actions.album_photos(album, include_hidden=can_manage_albums(request.auth, competition)).select_related(
        "album"
    )
    return _photos(request, qs, competition, page)


@router.get("/me/registrations", response=list[RegistrationAlbumOut], auth=auth)
def my_albums(request):
    regs = (
        CompetitionRegistration.objects.filter(
            looked_after(request.auth),
            is_rejected=False,
            competition__is_deleted=False,
            competition__external_albums__is_hidden=False,
        )
        .distinct()
        .select_related("competition", "category")
    )
    return [_registration_card(request, r) for r in regs if can_see_event(request.auth, r.competition)]


def _registration(user, registration_id) -> CompetitionRegistration:
    registration = get_object_or_404(CompetitionRegistration.objects.select_related("competition"), pk=registration_id)
    if not can_see_event(user, registration.competition) or not can_see_registration(user, registration):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return registration


@router.get("/registrations/{registration_id}/photos", response=PhotoPageOut, auth=auth)
def registration_photos(request, registration_id: int, page: int = 1):
    registration = _registration(request.auth, registration_id)
    qs = actions.registration_photos(registration).select_related("album")
    decisions = dict(PhotoDecision.objects.filter(registration=registration).values_list("photo_id", "state"))
    return _photos(request, qs, registration.competition, page, decisions)


def _archive(photos, name: str):
    if not photos.exists():
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    try:
        return archive_response(photos, name)
    except ArchiveTooBigError:
        raise HttpError(HTTPStatus.CONTENT_TOO_LARGE, "Too many photos for one archive") from None
    except ArchiveBusyError:
        busy = HttpResponse(status=HTTPStatus.SERVICE_UNAVAILABLE)
        busy["Retry-After"] = "60"
        return busy


@router.get("/registrations/{registration_id}/photos/archive", auth=auth, summary="A registration's photos as one ZIP")
def registration_archive(request, registration_id: int):
    registration = _registration(request.auth, registration_id)
    return _archive(
        actions.registration_photos(registration),
        f"{registration.competition.title} - {registration.display_name}",
    )


@router.get("/competitions/{competition_id}/photos/archive", auth=auth, summary="A bib's photos as one ZIP")
def bib_archive(request, competition_id: int, bib: str):
    competition = _competition(request.auth, competition_id)
    bib = bib.strip()[:32]
    if not bib:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    photos = actions.bib_photos(competition, bib).filter(album__in=visible_albums(request.auth, competition))
    return _archive(photos, bib_archive_name(competition, bib))


@router.post("/registrations/{registration_id}/photos/{photo_id}/decision", response=DecisionOut, auth=auth)
def decide(request, registration_id: int, photo_id: int, payload: DecisionIn):
    registration = _registration(request.auth, registration_id)
    if not can_mark(request.auth, registration):
        raise HttpError(HTTPStatus.FORBIDDEN, "Only the athlete or their representative marks photos")
    photo = actions.decision_photo(registration, photo_id, payload.state)
    if photo is None:
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    try:
        event = actions.decide(registration, photo, payload.state, request.auth)
    except actions.DecisionRefusedError as exc:
        raise HttpError(HTTPStatus.CONFLICT, str(exc)) from None
    if event is None and payload.state == PhotoDecision.State.NOT_ME:
        event = actions.recent_rejection(registration, photo)  # a retry keeps the original undo
    return {"state": payload.state, "event_id": event.pk if event else None}


@router.post("/registrations/{registration_id}/undo", response={HTTPStatus.NO_CONTENT: None}, auth=auth)
def undo(request, registration_id: int, payload: UndoIn):
    registration = _registration(request.auth, registration_id)
    if not can_mark(request.auth, registration):
        raise HttpError(HTTPStatus.FORBIDDEN, "Only the athlete or their representative marks photos")
    try:
        actions.undo(registration, payload.event_id, request.auth)
    except actions.DecisionRefusedError as exc:
        raise HttpError(HTTPStatus.CONFLICT, str(exc)) from None
    return Status(HTTPStatus.NO_CONTENT, None)


def _managed_album(user, album_id) -> ExternalAlbum:
    album = get_object_or_404(ExternalAlbum.objects.select_related("competition"), pk=album_id)
    if not can_manage_albums(user, album.competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    return album


@router.post("/competitions/{competition_id}/albums", response={HTTPStatus.CREATED: AlbumOut}, auth=auth)
def add_album(request, competition_id: int, payload: AlbumIn):
    competition = get_object_or_404(Competition, pk=competition_id, is_deleted=False)
    if not can_manage_albums(request.auth, competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    data = payload.dict()
    for lang in ("ru", "kk", "en"):
        data[f"title_{lang}"] = data[f"title_{lang}"] or getattr(competition, f"title_{lang}") or ""
    form = ExternalAlbumForm(data)
    if not form.is_valid():
        raise HttpError(
            HTTPStatus.UNPROCESSABLE_CONTENT,
            "; ".join(f"{k}: {' '.join(str(e) for e in v)}" for k, v in form.errors.items()),
        )
    album = form.save(commit=False)
    album.competition = competition
    album.created_by = request.auth
    album.title = album.title or competition.title
    album.save()
    try:
        actions.import_album(album, request.auth)
    except actions.ImportFailedError:
        pass  # the album is kept with last_error, as on the page; refresh once the index is there
    album.refresh_from_db()
    return Status(HTTPStatus.CREATED, album)


@router.post("/albums/{album_id}/refresh", response=AlbumOut, auth=auth)
def refresh(request, album_id: int):
    album = _managed_album(request.auth, album_id)
    try:
        actions.import_album(album, request.auth)
    except actions.ImportFailedError as exc:
        raise HttpError(HTTPStatus.UNPROCESSABLE_CONTENT, str(exc)) from None
    album.refresh_from_db()
    return album


@router.patch("/albums/{album_id}", response=AlbumOut, auth=auth)
def change_album(request, album_id: int, payload: AlbumPatchIn):
    album = _managed_album(request.auth, album_id)
    album.is_hidden = payload.is_hidden
    album.save(update_fields=["is_hidden"])
    return album


@router.delete("/albums/{album_id}", response={HTTPStatus.NO_CONTENT: None}, auth=auth)
def disconnect_album(request, album_id: int):
    _managed_album(request.auth, album_id).delete()  # the folder in Dropbox stays as it is
    return Status(HTTPStatus.NO_CONTENT, None)


@router.get("/competitions/{competition_id}/start-list-diagnostics", response=list[str], auth=auth)
def start_list_diagnostics(request, competition_id: int):
    """What the last start-list upload could not bind (foreign ids, conflicts, stage limits)."""
    competition = get_object_or_404(Competition, pk=competition_id, is_deleted=False)
    if not can_manage_albums(request.auth, competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    diagnostics = StartListDiagnostics.objects.filter(competition=competition).first()
    return diagnostics.warnings if diagnostics else []


@router.post("/photos/{photo_id}/hide", response={HTTPStatus.NO_CONTENT: None}, auth=auth)
def hide_photo(request, photo_id: int):
    return _set_hidden(request, photo_id, True)


@router.post("/photos/{photo_id}/show", response={HTTPStatus.NO_CONTENT: None}, auth=auth)
def show_photo(request, photo_id: int):
    return _set_hidden(request, photo_id, False)


def _set_hidden(request, photo_id: int, hidden: bool):
    photo = get_object_or_404(IndexedPhoto.objects.select_related("album__competition"), pk=photo_id)
    if not can_manage_albums(request.auth, photo.album.competition):
        raise HttpError(HTTPStatus.NOT_FOUND, "Not found")
    actions.set_photo_hidden(photo, hidden)
    return Status(HTTPStatus.NO_CONTENT, None)


@router.get("/albums/{album_id}/stats", response=StatsOut, auth=auth)
def album_stats(request, album_id: int):
    stats = actions.mark_stats(_managed_album(request.auth, album_id))
    return {**stats["totals"], "by_method": stats["by_method"]}
