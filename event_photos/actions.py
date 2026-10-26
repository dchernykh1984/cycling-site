"""What the pages and the API both do with event photos; neither carries its own copy of the rules."""

import hashlib
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from event_photos import index as index_module
from event_photos.dropbox import DropboxError, get_adapter
from event_photos.models import (
    BibObservation,
    ExternalAlbum,
    IndexedPhoto,
    IssuedBib,
    PhotoDecision,
    PhotoDecisionEvent,
)

INDEX_FILE = "photo-index.v1.json"


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
    data = get_adapter().thumbnail(photo.album.folder_url, photo.preview_path or photo.original_path)
    name = f"{photo.album_id}/{photo.pk}-{source[:16]}.jpg"
    path = _thumb_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free < settings.GALLERY_DISK_RESERVE_MB * 1024 * 1024:
        raise DropboxError("unavailable", "no disk space left for thumbnails")
    path.write_bytes(data)
    IndexedPhoto.objects.filter(
        pk=photo.pk, preview_sha256=photo.preview_sha256, original_sha256=photo.original_sha256
    ).update(thumb_file=name, thumb_source_sha256=source)
    return path


# -- matches ---------------------------------------------------------------------------------------


def visible_photos(album_qs) -> QuerySet:
    return IndexedPhoto.objects.filter(album__in=album_qs, in_index=True, is_hidden=False, album__is_hidden=False)


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
    """Participants' marks on an album, in numbers only: totals, and per method of the matched bib."""
    decided = BibObservation.objects.filter(photo__album=album_obj, photo__decisions__state__in=["me", "not_me"])
    by_method = decided.values("method").annotate(
        confirmed=Count("pk", filter=Q(photo__decisions__state="me")),
        rejected=Count("pk", filter=Q(photo__decisions__state="not_me")),
    )
    totals = PhotoDecision.objects.filter(photo__album=album_obj).aggregate(
        confirmed=Count("pk", filter=Q(state="me")), rejected=Count("pk", filter=Q(state="not_me"))
    )
    return {"totals": totals, "by_method": list(by_method)}
