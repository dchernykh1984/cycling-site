"""Event photos on the site: the event's albums and bib search, a registration's own album with its
"this is me" / "not me" marks, the organizer's page, and the thumbnails the site keeps."""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from calendar_app.models import Competition
from event_photos import actions
from event_photos.archive import Archive, ArchiveBusyError, ArchiveTooBigError
from event_photos.dropbox import DropboxError, preview_url
from event_photos.forms import ExternalAlbumForm
from event_photos.models import (
    THUMBNAIL_LIMIT_BYTES,
    ExternalAlbum,
    IndexedPhoto,
    IssuedBib,
    PhotoDecision,
    StartListDiagnostics,
)
from event_photos.permissions import can_manage_albums, can_mark, can_see_event, can_see_registration
from gallery.models import Album as GalleryAlbum
from registrations.models import CompetitionRegistration

PER_PAGE = 50
INDEXER_URL = "https://github.com/dchernykh1984/SportPhotoIndexer/releases/latest"
INDEXER_PROJECT_URL = "https://github.com/dchernykh1984/SportPhotoIndexer"


def _event(request, pk) -> Competition:
    competition = get_object_or_404(Competition, pk=pk)
    if not can_see_event(request.user, competition):
        raise Http404
    return competition


def visible_albums(user, competition):
    albums = ExternalAlbum.objects.filter(competition=competition)
    return albums if can_manage_albums(user, competition) else albums.filter(is_hidden=False)


def my_registrations(user, competition):
    """The registrations of this event whose albums ``user`` may open (their own, for now)."""
    if not user.is_authenticated:
        return CompetitionRegistration.objects.none()
    return CompetitionRegistration.objects.filter(competition=competition, user=user, is_rejected=False)


def _with_links(photos, competition):
    for photo in photos:
        photo.open_url = photo.original_view_url or preview_url(photo.album.folder_url, photo.file_name)
        # No thumbnail can be made for a big original without a preview: the card shows a placeholder.
        photo.thumb_url = (
            ""
            if photo.needs_preview
            else reverse("event_photos:thumb", args=[competition.pk, photo.pk, photo.source_sha256[:16]])
        )
    return photos


def archive_summary(photos, url: str) -> dict | None:
    """What the "Download all" button says: the archive's size, and whether it is under the limit."""
    totals = IndexedPhoto.objects.filter(pk__in=photos.order_by().values("pk")).aggregate(
        count=Count("pk"), size=Sum("original_bytes")
    )
    if not totals["count"]:
        return None
    return {"url": url, "size": totals["size"], "fits": totals["size"] <= settings.PHOTO_ARCHIVE_MAX_BYTES}


def archive_response(photos, name: str) -> StreamingHttpResponse:
    """The photos' originals as one ZIP, streamed; refused (ArchiveTooBigError, ArchiveBusyError)
    before anything is sent. The page and the API share it."""
    body = Archive(photos.select_related("album"))
    response = StreamingHttpResponse(body, content_type="application/zip")
    # A title typed with a line break would carry it into the saved file's name.
    response["Content-Disposition"] = content_disposition_header(True, f"{' '.join(name.split())}.zip")
    response["Cache-Control"] = "private, no-store"
    return response


def _archive_or_back(request, photos, name: str, back: str):
    if not photos.exists():
        raise Http404
    try:
        return archive_response(photos, name)
    except ArchiveTooBigError:
        messages.error(request, _("Too many photos for one archive: open them one by one."))
    except ArchiveBusyError:
        messages.error(request, _("Another archive is being made right now. Try again in a minute."))
    return redirect(back)


def participant_name(registration) -> str:
    if registration.participant_names:
        return str(registration)
    return f"{registration.last_name} {registration.first_name}"


def bib_archive_name(competition, bib: str) -> str:
    return _("%(event)s - bib %(bib)s") % {"event": competition.title, "bib": bib}


def _bib_query(request) -> str:
    return request.GET.get("bib", "").strip()[:32]


def event_photos(request, pk):
    """All the event's albums, and its photos found by a bib."""
    competition = _event(request, pk)
    albums = visible_albums(request.user, competition)
    bib = _bib_query(request)
    page = None
    archive = None
    if bib:
        found = actions.bib_photos(competition, bib).filter(album__in=albums).select_related("album")
        page = Paginator(found, PER_PAGE).get_page(request.GET.get("page"))
        _with_links(page, competition)
        archive = archive_summary(
            found, reverse("event_photos:bib_archive", args=[competition.pk]) + "?" + urlencode({"bib": bib})
        )
    return render(
        request,
        "event_photos/event_photos.html",
        {
            "competition": competition,
            "albums": albums,
            "bib": bib,
            "archive": archive,
            "photo_page_title": (_("Photos with bib %(bib)s") % {"bib": bib}) if bib else "",
            "photos": page,
            "registrations": my_registrations(request.user, competition),
            "registration_cards": [
                actions.registration_summary(r) for r in my_registrations(request.user, competition)
            ],
            # The club's curated albums of this event are photo sources too, with their own rights.
            "gallery_albums": GalleryAlbum.objects.visible_to(request.user).filter(competition=competition),
            "meta_title": _("Photos: %(event)s") % {"event": competition.title},
        },
    )


def album(request, pk, album_pk):
    competition = _event(request, pk)
    album_obj = get_object_or_404(visible_albums(request.user, competition), pk=album_pk)
    managing = can_manage_albums(request.user, competition)
    photos = actions.album_photos(album_obj, include_hidden=managing).select_related("album")
    page = Paginator(photos, PER_PAGE).get_page(request.GET.get("page"))
    _with_links(page, competition)
    return render(
        request,
        "event_photos/album.html",
        {
            "competition": competition,
            "album": album_obj,
            "photos": page,
            "can_manage": managing,
            "meta_title": album_obj.title,
        },
    )


def _registration(request, pk, reg_pk):
    competition = _event(request, pk)
    registration = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
    if not can_see_registration(request.user, registration):
        raise Http404
    return competition, registration


def _return_url(url, page, **query):
    """Keep a gallery's page after a POST; accept only a page number, never a destination."""
    try:
        number = int(page)
    except (ValueError, TypeError):
        number = 1
    if 1 < number < 2**31:
        query["page"] = number
    return url + ("?" + urlencode(query) if query else "")


@login_required
def registration_album(request, pk, reg_pk):
    competition, registration = _registration(request, pk, reg_pk)
    photos = actions.registration_photos(registration).select_related("album")
    page = Paginator(photos, PER_PAGE).get_page(request.GET.get("page"))
    _with_links(page, competition)
    decisions = dict(
        PhotoDecision.objects.filter(registration=registration, photo__in=list(page)).values_list("photo_id", "state")
    )
    for photo in page:
        photo.decision = decisions.get(photo.pk, "")
    confirmed = photos.filter(confirmed=True).count()
    undo_event = request.GET.get("undo", "")
    participant = participant_name(registration)
    title = (
        _("Photos with me: %(participant)s")
        if registration.user_id == request.user.pk
        else _("Photos of %(participant)s")
    ) % {"participant": participant}
    return render(
        request,
        "event_photos/registration_album.html",
        {
            "competition": competition,
            "registration": registration,
            "photo_page_title": title,
            "bibs": actions.registration_bibs(registration),
            "bib_in_conflict": IssuedBib.objects.filter(
                registration=registration, state=IssuedBib.State.CONFLICT
            ).exists(),
            "bib_needs_review": IssuedBib.objects.filter(
                registration=registration, state=IssuedBib.State.REVIEW
            ).exists(),
            "photos": page,
            "archive": archive_summary(
                photos, reverse("event_photos:registration_archive", args=[competition.pk, registration.pk])
            ),
            "confirmed_count": confirmed,
            "to_check_count": page.paginator.count - confirmed,
            "can_mark": can_mark(request.user, registration),
            "undo_event": undo_event if undo_event.isdigit() else "",
            "undo_page": request.GET.get("page", page.number),
            "meta_title": f"{title} - {competition.title}",
        },
    )


@login_required
def registration_archive(request, pk, reg_pk):
    """A registration's album as one ZIP of originals."""
    competition, registration = _registration(request, pk, reg_pk)
    return _archive_or_back(
        request,
        actions.registration_photos(registration),
        f"{competition.title} - {participant_name(registration)}",
        reverse("event_photos:registration", args=[competition.pk, registration.pk]),
    )


@login_required
def bib_archive(request, pk):
    """The photos found by a bib as one ZIP of originals; signed-in readers only, since every byte
    passes through the site."""
    competition = _event(request, pk)
    bib = _bib_query(request)
    if not bib:
        raise Http404
    photos = actions.bib_photos(competition, bib).filter(album__in=visible_albums(request.user, competition))
    back = reverse("event_photos:event", args=[competition.pk]) + "?" + urlencode({"bib": bib})
    return _archive_or_back(request, photos, bib_archive_name(competition, bib), back)


@login_required
@require_POST
def decide(request, pk, reg_pk, photo_pk):
    competition, registration = _registration(request, pk, reg_pk)
    if not can_mark(request.user, registration):
        raise Http404
    state = request.POST.get("state")
    if state not in (PhotoDecision.State.ME, PhotoDecision.State.NOT_ME):
        raise Http404
    photo = actions.decision_photo(registration, photo_pk, state)
    if photo is None:
        raise Http404
    url = reverse("event_photos:registration", args=[competition.pk, registration.pk])
    try:
        event = actions.decide(registration, photo, state, request.user)
    except actions.DecisionRefusedError as exc:
        messages.error(request, str(exc))
        return redirect(_return_url(url, request.POST.get("page")))
    if state == PhotoDecision.State.NOT_ME:
        event = event or actions.recent_rejection(registration, photo)
        query = {"undo": event.pk} if event else {}
        return redirect(_return_url(url, request.POST.get("page"), **query))
    return redirect(f"{_return_url(url, request.POST.get('page'))}#photo-{photo.pk}")


@login_required
@require_POST
def undo(request, pk, reg_pk):
    competition, registration = _registration(request, pk, reg_pk)
    if not can_mark(request.user, registration):
        raise Http404
    try:
        actions.undo(registration, int(request.POST.get("event", "0") or 0), request.user)
    except (actions.DecisionRefusedError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect(
        _return_url(
            reverse("event_photos:registration", args=[competition.pk, registration.pk]), request.POST.get("page")
        )
    )


def thumb(request, pk, photo_pk, digest):
    return thumbnail_response(request.user, _event(request, pk), photo_pk)


def thumbnail_response(user, competition, photo_pk) -> FileResponse | HttpResponse:
    """A photo's thumbnail for ``user``, by the album's visibility; the page and the API share it."""
    photo = get_object_or_404(
        IndexedPhoto.objects.select_related("album"),
        pk=photo_pk,
        album__in=visible_albums(user, competition),
        in_index=True,
    )
    if photo.is_hidden and not can_manage_albums(user, competition):
        raise Http404
    try:
        path = actions.thumbnail_path(photo)
        response = FileResponse(path.open("rb"), content_type="image/jpeg")
    except (DropboxError, FileNotFoundError) as exc:
        if isinstance(exc, DropboxError) and exc.kind not in ("busy", "throttled", "unavailable"):
            raise Http404 from None
        unavailable = HttpResponse(status=503)
        unavailable["Retry-After"] = str(min(exc.retry_after or 2, 60) if isinstance(exc, DropboxError) else 1)
        unavailable["Cache-Control"] = "private, no-store"
        return unavailable
    # Private: no shared cache may keep a thumbnail of an album that is hidden later.
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
def manage(request, pk):
    competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
    if not can_manage_albums(request.user, competition):
        raise Http404
    if request.method == "POST":
        form = ExternalAlbumForm(request.POST)
        if form.is_valid():
            album_obj = form.save(commit=False)
            album_obj.competition = competition
            album_obj.created_by = request.user
            if not album_obj.title:
                album_obj.title = competition.title
            album_obj.save()
            _refresh(request, album_obj)
            return redirect("event_photos:manage", competition.pk)
    else:
        form = ExternalAlbumForm(
            initial={
                "title_ru": competition.title_ru,
                "title_kk": competition.title_kk,
                "title_en": competition.title_en,
            }
        )
    albums = list(ExternalAlbum.objects.filter(competition=competition))
    for album_obj in albums:
        album_obj.stats = actions.mark_stats(album_obj)
        album_obj.needs_preview = [
            p.original_path
            for p in album_obj.photos.filter(in_index=True, preview_path="", original_bytes__gt=THUMBNAIL_LIMIT_BYTES)
        ]
    diagnostics = StartListDiagnostics.objects.filter(competition=competition).first()
    return render(
        request,
        "event_photos/manage.html",
        {
            "competition": competition,
            "form": form,
            "albums": albums,
            "guide_url": reverse("event_photos:guide"),
            "max_photos": settings.PHOTO_INDEX_MAX_PHOTOS,
            "max_mb": settings.PHOTO_INDEX_MAX_BYTES // 1_000_000,
            "start_list_warnings": diagnostics.warnings if diagnostics else [],
            "meta_title": _("Event photos"),
        },
    )


def _refresh(request, album_obj) -> None:
    try:
        changed = actions.import_album(album_obj, request.user)
    except actions.ImportFailedError as exc:
        messages.error(request, _("The index was not imported: %(error)s") % {"error": exc})
        return
    if changed:
        messages.success(request, _("Participants' tagging is up to date."))
    else:
        messages.info(request, _("Nothing new in the index."))


@login_required
@require_POST
def photo_action(request, pk, photo_pk):
    """Hide or show one photo; the mark is the site's own and survives every import."""
    competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
    if not can_manage_albums(request.user, competition):
        raise Http404
    photo = get_object_or_404(IndexedPhoto, pk=photo_pk, album__competition=competition)
    if request.POST.get("action") in ("hide", "show"):
        actions.set_photo_hidden(photo, request.POST["action"] == "hide")
    url = _return_url(reverse("event_photos:album", args=[competition.pk, photo.album_id]), request.POST.get("page"))
    return redirect(f"{url}#photo-{photo.pk}")


@login_required
@require_POST
def album_action(request, pk, album_pk):
    competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
    if not can_manage_albums(request.user, competition):
        raise Http404
    album_obj = get_object_or_404(ExternalAlbum, pk=album_pk, competition=competition)
    action = request.POST.get("action")
    if action == "refresh":
        _refresh(request, album_obj)
    elif action in ("hide", "show"):
        album_obj.is_hidden = action == "hide"
        album_obj.save(update_fields=["is_hidden"])
    elif action == "delete":
        album_obj.delete()  # the files in Dropbox stay where they are
    return redirect("event_photos:manage", competition.pk)


def guide(request):
    """How to prepare an album: steps, and the limits the import really applies (same settings)."""
    return render(
        request,
        "event_photos/guide.html",
        {
            "indexer_url": INDEXER_URL,
            "indexer_project_url": INDEXER_PROJECT_URL,
            "max_photos": settings.PHOTO_INDEX_MAX_PHOTOS,
            "max_bibs": settings.PHOTO_INDEX_MAX_BIBS_PER_PHOTO,
            "max_mb": settings.PHOTO_INDEX_MAX_BYTES // 1_000_000,
            "meta_title": _("How to prepare a photo album for the site"),
        },
    )


def sample_index(request):
    """A small example of photo-index.v1.json to download."""
    from django.http import HttpResponse

    from event_photos.index import SAMPLE

    response = HttpResponse(SAMPLE, content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="photo-index.v1.json"'
    return response
