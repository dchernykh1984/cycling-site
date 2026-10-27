"""What the pages and the API both do with event photos; neither carries its own copy of the rules."""

import hashlib
import shutil
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import BoundedSemaphore

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from event_photos import index as index_module
from event_photos.dropbox import DropboxError, get_adapter
from event_photos.models import (
    THUMBNAIL_LIMIT_BYTES,
    BibObservation,
    ExternalAlbum,
    IndexedPhoto,
    IssuedBib,
    PhotoDecision,
    PhotoDecisionEvent,
)

INDEX_FILE = "photo-index.v1.json"
_THUMBNAIL_SLOTS = BoundedSemaphore(2)


class ImportFailedError(Exception):
    pass


# -- import ----------------------------------------------------------------------------------------


def import_album(album: ExternalAlbum, user) -> bool:
    """Read the folder's index and publish it; False when it was already the published snapshot.

    Reading and checking happen outside the transaction; the revision is compared again under the
    album's row lock, so of two imports racing the older snapshot can never land last. Any failure
    leaves the last published state and records the reason on the album.
    """
    try:
        raw = get_adapter().read_file(album.folder_url, INDEX_FILE)
        parsed = index_module.parse(raw, hashlib.sha256(raw).hexdigest())
        return _publish(album.pk, parsed, user)
    except (DropboxError, index_module.IndexValidationError, ImportFailedError) as exc:
        ExternalAlbum.objects.filter(pk=album.pk).update(last_error=str(exc)[:1000])
        album.last_error = str(exc)[:1000]
        raise ImportFailedError(str(exc)) from exc


def _publish(album_pk: int, parsed: index_module.Index, user) -> bool:
    stale_thumbs: list[str] = []
    with transaction.atomic():
        album = ExternalAlbum.objects.select_for_update().get(pk=album_pk)
        if album.album_uuid and album.album_uuid != parsed.album_uuid:
            raise ImportFailedError("album_id: this folder's index names a different album than before")
        taken = ExternalAlbum.objects.filter(album_uuid=parsed.album_uuid).exclude(pk=album.pk).first()
        if taken is not None:
            raise ImportFailedError(f'album_id: already connected as "{taken.title}" ({taken.competition})')
        existing = {p.photo_uuid: p for p in album.photos.all()}
        live = {u for u, p in existing.items() if p.in_index}
        if not index_module.check_successor(parsed, revision=album.revision, sha256=album.index_sha256, live=live):
            return False
        to_create: list[IndexedPhoto] = []
        to_update: list[IndexedPhoto] = []
        for item in parsed.photos:
            row = existing.get(item.uuid) or IndexedPhoto(album=album, photo_uuid=item.uuid)
            new_source = item.preview_sha256 or item.original_sha256
            if row.thumb_file and row.thumb_source_sha256 != new_source:
                stale_thumbs.append(row.thumb_file)
                row.thumb_file, row.thumb_source_sha256 = "", ""
            row.original_path = item.original_path
            row.original_sha256 = item.original_sha256
            row.original_bytes = item.original_bytes
            row.original_view_url = item.original_view_url
            row.preview_path = item.preview_path
            row.preview_sha256 = item.preview_sha256
            row.processing_state = item.processing_state
            row.in_index = True
            (to_update if row.pk else to_create).append(row)
        for uuid_ in parsed.removed & set(existing):
            existing[uuid_].in_index = False
            to_update.append(existing[uuid_])
        IndexedPhoto.objects.bulk_create(to_create, batch_size=500)
        fields = [
            "original_path",
            "original_sha256",
            "original_bytes",
            "original_view_url",
            "preview_path",
            "preview_sha256",
            "processing_state",
            "in_index",
            "thumb_file",
            "thumb_source_sha256",
        ]
        IndexedPhoto.objects.bulk_update(to_update, fields, batch_size=500)
        by_uuid = {p.photo_uuid: p for p in album.photos.all()}
        BibObservation.objects.filter(photo__album=album).delete()
        BibObservation.objects.bulk_create(
            [
                BibObservation(
                    photo=by_uuid[item.uuid], value=b.value, state=b.state, method=b.method, confidence=b.confidence
                )
                for item in parsed.photos
                for b in item.bibs
            ],
            batch_size=1000,
        )
        album.album_uuid = parsed.album_uuid
        album.revision = parsed.revision
        album.index_sha256 = parsed.sha256
        album.inventory_complete = parsed.inventory_complete
        album.photo_count = len(parsed.photos)
        album.processed_count = sum(p.processing_state == "processed" for p in parsed.photos)
        album.imported_at = timezone.now()
        album.imported_by = user if getattr(user, "is_authenticated", False) else None
        album.last_error = ""
        album.save()
        transaction.on_commit(lambda: _delete_thumbs(stale_thumbs))
    return True


# -- thumbnails ------------------------------------------------------------------------------------


def _thumb_root() -> Path:
    return Path(settings.MEDIA_ROOT) / settings.PRIVATE_MEDIA_PREFIX / "event_photos"


def _delete_thumbs(names: list[str]) -> None:
    for name in names:
        (_thumb_root() / name).unlink(missing_ok=True)


def thumbnail_path(photo: IndexedPhoto) -> Path:
    """The site's copy of a photo's thumbnail, fetched from Dropbox the first time it is asked for.

    Named by the site's own ids and the source digest, never by ids taken from an index; attached only
    while that digest is still the photo's, so a fetch racing a newer import cannot stick.
    """
    source = photo.source_sha256
    if photo.thumb_file and photo.thumb_source_sha256 == source:
        path = _thumb_root() / photo.thumb_file
        if path.exists():
            return path
    if photo.needs_preview:
        raise DropboxError("unsupported", "the original is too big for a Dropbox thumbnail and has no preview")
    # Never let external storage occupy all four web threads, including for API callers.
    if not _THUMBNAIL_SLOTS.acquire(blocking=False):
        raise DropboxError("busy", retry_after=1)
    try:
        data = get_adapter().thumbnail(photo.album.folder_url, photo.preview_path or photo.original_path)
    finally:
        _THUMBNAIL_SLOTS.release()
    name = f"{photo.album_id}/{photo.pk}-{source[:16]}.jpg"
    path = _thumb_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free < settings.GALLERY_DISK_RESERVE_MB * 1024 * 1024:
        raise DropboxError("unavailable", "no disk space left for thumbnails")
    # Other web threads may already be reading this name: publish only a complete image.
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            temporary.write(data)
            temporary.close()
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
    IndexedPhoto.objects.filter(
        pk=photo.pk, preview_sha256=photo.preview_sha256, original_sha256=photo.original_sha256
    ).update(thumb_file=name, thumb_source_sha256=source)
    return path


def set_photo_hidden(photo: IndexedPhoto, hidden: bool) -> None:
    IndexedPhoto.objects.filter(pk=photo.pk).update(is_hidden=hidden)


# -- matches ---------------------------------------------------------------------------------------


def visible_photos(album_qs) -> QuerySet:
    return IndexedPhoto.objects.filter(album__in=album_qs, in_index=True, is_hidden=False, album__is_hidden=False)


def album_photos(album, *, include_hidden: bool = False) -> QuerySet:
    """An album's inventory, including hidden photos only for its managers."""
    if include_hidden:
        return album.photos.filter(in_index=True)
    return visible_photos(ExternalAlbum.objects.filter(pk=album.pk))


def registration_bibs(registration) -> list[str]:
    """The bibs a registration holds; none while they are in conflict."""
    return list(
        IssuedBib.objects.filter(registration=registration)
        .exclude(state=IssuedBib.State.CONFLICT)
        .values_list("bib", flat=True)
    )


def registration_photos(registration) -> QuerySet:
    """A registration's album: its bibs' accepted matches and candidates, plus its own "this is me",
    minus its own "not me". Annotated with ``decision`` (me / not_me / None) and ``confirmed``."""
    bibs = registration_bibs(registration)
    albums = ExternalAlbum.objects.filter(competition_id=registration.competition_id)
    mine = PhotoDecision.objects.filter(registration=registration, photo=OuterRef("pk"))
    matched = Q(bibs__value__in=bibs, bibs__state__in=["accepted", "candidate"])
    return (
        visible_photos(albums)
        .filter(matched | Q(decisions__registration=registration, decisions__state=PhotoDecision.State.ME))
        .exclude(Exists(mine.filter(state=PhotoDecision.State.NOT_ME)))
        .annotate(
            confirmed=Exists(mine.filter(state=PhotoDecision.State.ME))
            | Exists(BibObservation.objects.filter(photo=OuterRef("pk"), value__in=bibs, state="accepted"))
        )
        .distinct()
        .order_by("-confirmed", "original_path", "pk")
    )


def registration_summary(registration) -> dict:
    """What a registration's photo card shows: its bibs, my counts, a cover from my own photos,
    and a state while there is nothing to show yet. Database only -- no call to Dropbox."""
    bibs = registration_bibs(registration)
    conflict = IssuedBib.objects.filter(registration=registration, state=IssuedBib.State.CONFLICT).exists()
    photos = registration_photos(registration)
    count = photos.count()
    confirmed = photos.filter(confirmed=True).count() if count else 0
    albums = ExternalAlbum.objects.filter(competition_id=registration.competition_id, is_hidden=False)
    indexing = any(not a.inventory_complete or a.processed_count < a.photo_count for a in albums)
    if conflict and not bibs:
        state = "conflict"
    elif not bibs:
        state = "no-bib"
    elif IssuedBib.objects.filter(registration=registration, state=IssuedBib.State.REVIEW).exists():
        state = "review"
    elif indexing:
        state = "indexing"
    else:
        state = "ready"
    return {
        "registration": registration,
        "bibs": bibs,
        "count": count,
        "confirmed": confirmed,
        "to_check": count - confirmed,
        "cover": photos.filter(confirmed=True)  # type: ignore[misc]  # annotated
        .filter(~Q(preview_path="") | Q(original_bytes__lte=THUMBNAIL_LIMIT_BYTES))
        .select_related("album")
        .first()
        if count
        else None,
        "state": state,
    }


def bib_photos(competition, bib: str) -> QuerySet:
    """Event search by bib: accepted matches and "this is me" of a registration holding the bib, less
    the photos every registration holding it marked "not me" (a team-mate's mark never hides it)."""
    bib = index_module.normalize_bib(bib)
    holders = list(
        IssuedBib.objects.filter(competition=competition, bib=bib)
        .exclude(state=IssuedBib.State.CONFLICT)
        .values_list("registration_id", flat=True)
    )
    albums = ExternalAlbum.objects.filter(competition=competition)
    qs = visible_photos(albums).filter(
        Q(bibs__value=bib, bibs__state="accepted")
        | Q(decisions__registration_id__in=holders, decisions__state=PhotoDecision.State.ME)
    )
    if holders:
        rejections = (
            PhotoDecision.objects.filter(
                photo=OuterRef("pk"), registration_id__in=holders, state=PhotoDecision.State.NOT_ME
            )
            .values("photo")
            .annotate(n=Count("pk"))
            .values("n")
        )
        qs = qs.annotate(rejections=Coalesce(Subquery(rejections, output_field=IntegerField()), 0)).exclude(
            rejections=len(holders)
        )
    return qs.distinct().order_by("original_path", "pk")


# -- decisions -------------------------------------------------------------------------------------


class DecisionRefusedError(Exception):
    pass


def decision_photo(registration, photo_pk: int, state: str) -> IndexedPhoto | None:
    """A mark's visible target, including an already rejected photo for an idempotent retry."""
    if (
        state == PhotoDecision.State.NOT_ME
        and PhotoDecision.objects.filter(registration=registration, photo_id=photo_pk, state=state).exists()
    ):
        return (
            visible_photos(ExternalAlbum.objects.filter(competition_id=registration.competition_id))
            .filter(pk=photo_pk)
            .first()
        )
    return registration_photos(registration).filter(pk=photo_pk).first()


def recent_rejection(registration, photo) -> PhotoDecisionEvent | None:
    """Keep the original undo link on a retry, without creating a new event or restarting its clock."""
    return (
        PhotoDecisionEvent.objects.filter(
            decision__registration=registration,
            decision__photo=photo,
            decision__state=PhotoDecision.State.NOT_ME,
            to_state=PhotoDecision.State.NOT_ME,
            undone_at=None,
            at__gte=timezone.now() - timedelta(seconds=settings.PHOTO_DECISION_UNDO_SECONDS),
        )
        .order_by("-pk")
        .first()
    )


def decide(registration, photo: IndexedPhoto, state: str, actor) -> PhotoDecisionEvent | None:
    """Set "this is me" / "not me"; a cross is final, and repeating the same mark changes nothing."""
    with transaction.atomic():
        decision, _ = PhotoDecision.objects.select_for_update().get_or_create(
            registration=registration, photo=photo, defaults={"state": "", "version": 0}
        )
        if decision.state == state:
            return None
        if decision.state == PhotoDecision.State.NOT_ME:
            raise DecisionRefusedError('a photo marked "not me" cannot be changed')
        event = PhotoDecisionEvent.objects.create(
            decision=decision, from_state=decision.state, to_state=state, actor=actor
        )
        decision.state = state
        decision.version += 1
        decision.save(update_fields=["state", "version"])
        return event


def undo(registration, event_id: int, actor) -> None:
    """Revert one change, only while it is the latest for its photo and inside the undo window."""
    with transaction.atomic():
        event = (
            PhotoDecisionEvent.objects.select_related("decision")
            .filter(pk=event_id, decision__registration=registration, undone_at=None)
            .first()
        )
        if event is None:
            raise DecisionRefusedError("nothing to undo")
        decision = PhotoDecision.objects.select_for_update().get(pk=event.decision_id)
        latest = decision.events.filter(undone_at=None).order_by("-pk").first()
        if latest is None or latest.pk != event.pk:
            raise DecisionRefusedError("a newer mark was made since")
        if timezone.now() - event.at > timedelta(seconds=settings.PHOTO_DECISION_UNDO_SECONDS):
            raise DecisionRefusedError("too late to undo")
        event.undone_at = timezone.now()
        event.save(update_fields=["undone_at"])
        decision.state = event.from_state
        decision.version += 1
        decision.save(update_fields=["state", "version"])


# -- organizer statistics --------------------------------------------------------------------------


def mark_stats(album_obj) -> dict:
    """Participants' marks on an album, in numbers only.

    A mark counts for a method only through the observation of the marking registration's own
    bib on that photo -- another bib on the same frame was not checked by this mark. ``unchecked``
    is the photos with a bib on them that nobody has marked yet.
    """
    decisions = list(
        PhotoDecision.objects.filter(photo__album=album_obj, state__in=["me", "not_me"]).values_list(
            "registration_id", "photo_id", "state"
        )
    )
    bibs_of: dict[int, set[str]] = {}
    for reg, bib in IssuedBib.objects.filter(registration_id__in={d[0] for d in decisions}).values_list(
        "registration_id", "bib"
    ):
        bibs_of.setdefault(reg, set()).add(bib)
    observations: dict[int, list[tuple[str, str]]] = {}
    for photo, value, method in BibObservation.objects.filter(photo_id__in={d[1] for d in decisions}).values_list(
        "photo_id", "value", "method"
    ):
        observations.setdefault(photo, []).append((value, method))
    by_method: dict[str, dict[str, int | str]] = {}
    for reg, photo, state in decisions:
        for value, method in observations.get(photo, []):
            if value in bibs_of.get(reg, set()):
                row = by_method.setdefault(method, {"method": method, "confirmed": 0, "rejected": 0})
                key = "confirmed" if state == "me" else "rejected"
                row[key] = int(row[key]) + 1
    unchecked = (
        IndexedPhoto.objects.filter(album=album_obj, in_index=True, bibs__state__in=["accepted", "candidate"])
        .exclude(decisions__state__in=["me", "not_me"])
        .distinct()
        .count()
    )
    return {
        "totals": {
            "confirmed": sum(d[2] == "me" for d in decisions),
            "rejected": sum(d[2] == "not_me" for d in decisions),
            "unchecked": unchecked,
        },
        "by_method": sorted(by_method.values(), key=lambda row: row["method"]),
    }
