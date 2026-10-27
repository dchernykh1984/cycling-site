"""One ZIP of photos' originals, streamed while they are read from storage: nothing reaches the disk.

The originals live only in the organizer's folder, so every byte of an archive passes through the
site. One archive is made at a time per web process, leaving its other threads for pages, marks and
thumbnails; each original is held in memory once, while it is written.
"""

import time
import zipfile
from threading import BoundedSemaphore

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from event_photos.dropbox import DropboxError, get_adapter, preview_url

_SLOTS = BoundedSemaphore(1)
# A storage hiccup is waited out once, briefly: the reader is watching the download.
_RETRY_KINDS = ("throttled", "unavailable")
_MAX_RETRY_WAIT = 10


class ArchiveBusyError(Exception):
    pass


class ArchiveTooBigError(Exception):
    pass


class _Sink:
    """The unseekable stream the ZIP is written into; drained into the response after each file."""

    def __init__(self):
        self._chunks: list[bytes] = []

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def drain(self):
        chunks, self._chunks = self._chunks, []
        yield from chunks


def open_url(photo) -> str:
    return photo.original_view_url or preview_url(photo.album.folder_url, photo.file_name)


def total_bytes(photos) -> int:
    return sum(photo.original_bytes for photo in photos)


class Archive:
    """The response body: iterate it once; ``close()`` -- which Django calls when the response ends
    or the reader leaves -- frees the slot."""

    def __init__(self, photos):
        self.photos = list(photos)
        if total_bytes(self.photos) > settings.PHOTO_ARCHIVE_MAX_BYTES:
            raise ArchiveTooBigError
        if not _SLOTS.acquire(blocking=False):
            raise ArchiveBusyError
        self._holding = True
        self.language = translation.get_language()

    def __iter__(self):
        return self._chunks()

    def close(self) -> None:
        if self._holding:
            self._holding = False
            _SLOTS.release()

    def _read(self, photo) -> bytes | None:
        if photo.original_bytes > settings.PHOTO_ARCHIVE_MAX_FILE_BYTES:
            return None
        for attempt in (1, 2):
            try:
                return get_adapter().read_file(
                    photo.album.folder_url, photo.original_path, limit=settings.PHOTO_ARCHIVE_MAX_FILE_BYTES
                )
            except DropboxError as exc:
                if attempt == 2 or exc.kind not in _RETRY_KINDS:
                    return None
                time.sleep(min(exc.retry_after or 2, _MAX_RETRY_WAIT))
        return None

    def _chunks(self):
        sink = _Sink()
        missing = []
        names: set[str] = set()
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as archive:
            for photo in self.photos:
                data = self._read(photo)
                if data is None:
                    missing.append(photo)
                    continue
                archive.writestr(_unique(photo.file_name, names), data)
                yield from sink.drain()
            if missing:
                with translation.override(self.language):
                    note = "\n".join(
                        [_("These photos are not in the archive; open them by their links:"), ""]
                        + [f"{photo.file_name}  {open_url(photo)}" for photo in missing]
                    )
                    archive.writestr(_unique(_("missing-photos.txt"), names), note + "\n")
        yield from sink.drain()


def _unique(name: str, taken: set[str]) -> str:
    """Two photographers may both have an IMG_0001.jpg: the second becomes IMG_0001-2.jpg."""
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    candidate, number = name, 1
    while candidate.lower() in taken:
        number += 1
        candidate = f"{stem}-{number}{dot}{extension}"
    taken.add(candidate.lower())
    return candidate
