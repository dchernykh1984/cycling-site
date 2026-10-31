"""Checking a photo-index.v1.json before anything of it is stored (contracts/photo-index.md).

Pure functions, no database: ``parse`` turns the bytes into an ``Index`` or raises ``IndexValidationError``
naming the offending field; ``check_successor`` compares it with what the album already published.
The site checks the index's structure because that protects the site; whether its bibs are right is
for the participants' own marks to settle.
"""

import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import NoReturn

from django.conf import settings

from event_photos.models import BibObservation

SCHEMA_VERSION = 1
_SHA = re.compile(r"^[0-9a-f]{64}\Z")
_PREVIEW_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MEDIA_TYPES = _PREVIEW_TYPES | {
    "image/heic",
    "image/heif",
    "image/tiff",
    "image/bmp",
    "image/gif",
    "image/avif",
}
_PROCESSING = {"pending", "processed", "failed"}
_STATES = set(BibObservation.State.values)
_METHODS = {"ocr", "appearance", "manual"}
_VIEW_URL = re.compile(r"^https://(www\.dropbox\.com|dl\.dropboxusercontent\.com)/scl/fi/[^\s]+\Z")
_MAX_PATH = 500


class IndexValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Bib:
    value: str
    state: str
    method: str
    confidence: float | None


@dataclass(frozen=True)
class Photo:
    uuid: uuid.UUID
    original_path: str
    original_sha256: str
    original_bytes: int
    original_view_url: str
    preview_path: str
    preview_sha256: str
    processing_state: str
    bibs: tuple[Bib, ...]


@dataclass(frozen=True)
class Index:
    album_uuid: uuid.UUID
    revision: int
    sha256: str
    inventory_complete: bool
    photos: tuple[Photo, ...]
    removed: frozenset[uuid.UUID] = field(default_factory=frozenset)


def normalize_bib(value: str) -> str:
    """``trim-nfc-exact-v1``: trim and NFC only; leading zeroes, letters and case are kept."""
    return unicodedata.normalize("NFC", value.strip())


def _fail(where: str, why: str) -> NoReturn:
    raise IndexValidationError(f"{where}: {why}")


def _uuid(value, where: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        _fail(where, "not a UUID")


def _path(value, where: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_PATH:
        _fail(where, "missing or too long")
    if any(ord(c) < 32 or c in "\\\x7f" for c in value) or value.startswith("/") or "://" in value:
        _fail(where, "not a safe relative path")
    if any(part in ("", ".", "..") for part in value.split("/")):
        _fail(where, "not a safe relative path")
    return unicodedata.normalize("NFC", value)


def _asset(value, where: str, *, view_url: bool) -> tuple[str, str, int, str]:
    if not isinstance(value, dict):
        _fail(where, "missing")
    path = _path(value.get("path"), f"{where}.path")
    sha = value.get("sha256")
    if not isinstance(sha, str) or not _SHA.match(sha):
        _fail(f"{where}.sha256", "must be the file's SHA-256, 64 lowercase hex digits")
    size = value.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size < 2**63:
        _fail(f"{where}.bytes", "must be a positive integer")
    if not isinstance(value.get("media_type"), str) or value["media_type"] not in _MEDIA_TYPES:
        _fail(f"{where}.media_type", "must be a supported photo format")
    url = value.get("view_url", "")
    if not isinstance(url, str) or (url and not (view_url and len(url) <= _MAX_PATH and _VIEW_URL.match(url))):
        _fail(f"{where}.view_url", "must be a Dropbox shared file link")
    return path, sha, size, url


def _bib(value, where: str, original_sha: str) -> Bib:
    if not isinstance(value, dict):
        _fail(where, "not an object")
    raw = value.get("value")
    if not isinstance(raw, str):
        _fail(f"{where}.value", "must be text")
    bib = normalize_bib(raw)
    if not 1 <= len(bib) <= 32 or any(unicodedata.category(c).startswith("C") for c in bib):
        _fail(f"{where}.value", "must be 1 to 32 printable characters")
    state, method = value.get("state"), value.get("method")
    if not isinstance(state, str) or state not in _STATES:
        _fail(f"{where}.state", "must be candidate, accepted or rejected")
    if not isinstance(method, str) or method not in _METHODS:
        _fail(f"{where}.method", "must be ocr, appearance or manual")
    if method == "appearance" and state != BibObservation.State.CANDIDATE:
        _fail(f"{where}.state", "an appearance match is always a candidate")
    if method == "manual" and value.get("content_sha256") != original_sha:
        _fail(f"{where}.content_sha256", "a manual decision must name the original's SHA-256")
    confidence = value.get("confidence")
    if confidence is not None and not (isinstance(confidence, int | float) and 0 <= confidence <= 1):
        _fail(f"{where}.confidence", "must be between 0 and 1")
    if "region" in value:
        _region(value["region"], f"{where}.region")
    return Bib(bib, state, method, None if confidence is None else float(confidence))


def _region(region, where):
    if not isinstance(region, dict):
        _fail(where, "must be an x, y, w, h object")
    values = [region.get(key) for key in ("x", "y", "w", "h")]
    if any(type(v) not in (int, float) or not 0 <= v <= 1 for v in values):
        _fail(where, "coordinates must be fractions between 0 and 1")
    x, y, w, h = values
    if not w or not h or x + w > 1.000001 or y + h > 1.000001:
        _fail(where, "box must fit inside the image")


def _manual_review(photo, where, sha):
    review = photo.get("manual_review")
    if review is None:
        return
    if not isinstance(review, dict) or review.get("original_sha256") != sha:
        _fail(f"{where}.manual_review", "must name the reviewed original's SHA-256")
    if not isinstance(review.get("lock_accepted_set"), bool):
        _fail(f"{where}.manual_review.lock_accepted_set", "must be true or false")
    review_id = review.get("review_id")
    if not isinstance(review_id, str) or not 1 <= len(review_id) <= 100:
        _fail(f"{where}.manual_review.review_id", "must be a nonempty correction ID")
    if review["lock_accepted_set"]:
        accepted = {
            normalize_bib(b["value"])
            for b in photo.get("bibs", [])
            if b["method"] == "manual" and b["state"] == BibObservation.State.ACCEPTED
        }
        if any(
            b["state"] == BibObservation.State.ACCEPTED and normalize_bib(b["value"]) not in accepted
            for b in photo.get("bibs", [])
        ):
            _fail(f"{where}.bibs", "automatic matches cannot extend the manually accepted set")


def _no_nul(value, where: str) -> None:
    """PostgreSQL text cannot hold NUL, and JSON can smuggle one in as an escape."""
    if isinstance(value, str) and "\x00" in value:
        _fail(where, "contains a NUL character")
    if isinstance(value, str) and any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        _fail(where, "contains an unpaired Unicode surrogate")
    if isinstance(value, dict):
        for key, item in value.items():
            _no_nul(key, f"{where} key")
            _no_nul(item, f"{where}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _no_nul(item, f"{where}[{i}]")


def _load(raw: bytes) -> dict:
    if len(raw) > settings.PHOTO_INDEX_MAX_BYTES:
        _fail("index", f"larger than {settings.PHOTO_INDEX_MAX_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
        data = json.loads(text)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        _fail("index", f"not UTF-8 JSON ({exc})")
    if not isinstance(data, dict):
        _fail("index", "not a JSON object")
    try:
        _no_nul(data, "index")
    except RecursionError:
        _fail("index", "nested too deeply")
    _header(data)
    return data


def _header(data: dict) -> None:
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version", f"only version {SCHEMA_VERSION} is supported")
    revision = data.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or not 1 <= revision < 2**63:
        _fail("revision", "must be a positive integer")
    if data.get("bib_normalization") != "trim-nfc-exact-v1":
        _fail("bib_normalization", "must be trim-nfc-exact-v1")
    processing = data.get("processing")
    if not isinstance(processing, dict) or not isinstance(processing.get("inventory_complete"), bool):
        _fail("processing.inventory_complete", "must be true or false")
    photos = data.get("photos")
    if not isinstance(photos, list):
        _fail("photos", "must be a list")
    if len(photos) > settings.PHOTO_INDEX_MAX_PHOTOS:
        _fail("photos", f"more than {settings.PHOTO_INDEX_MAX_PHOTOS} photos")


def _photo(p, where: str) -> Photo:
    if not isinstance(p, dict):
        _fail(where, "not an object")
    pid = _uuid(p.get("id"), f"{where}.id")
    o_path, o_sha, o_bytes, o_url = _asset(p.get("original"), f"{where}.original", view_url=True)
    pv_path, pv_sha = "", ""
    if p.get("preview") is not None:
        pv_path, pv_sha, _, _ = _asset(p["preview"], f"{where}.preview", view_url=True)
        if p["preview"]["media_type"] not in _PREVIEW_TYPES:
            _fail(f"{where}.preview.media_type", "must be image/jpeg, image/png or image/webp")
    if p["original"]["media_type"] not in _PREVIEW_TYPES and not pv_path:
        _fail(f"{where}.preview", "required for this original format")
    state = p.get("processing_state")
    if not isinstance(state, str) or state not in _PROCESSING:
        _fail(f"{where}.processing_state", "must be pending, processed or failed")
    bibs_raw = p.get("bibs", [])
    if not isinstance(bibs_raw, list) or len(bibs_raw) > settings.PHOTO_INDEX_MAX_BIBS_PER_PHOTO:
        _fail(f"{where}.bibs", f"must be a list of at most {settings.PHOTO_INDEX_MAX_BIBS_PER_PHOTO}")
    bibs = tuple(_bib(b, f"{where}.bibs[{j}]", o_sha) for j, b in enumerate(bibs_raw))
    _manual_review(p, where, o_sha)
    return Photo(pid, o_path, o_sha, o_bytes, o_url, pv_path, pv_sha, state, bibs)


def parse(raw: bytes, sha256: str) -> Index:
    data = _load(raw)
    album_uuid = _uuid(data.get("album_id"), "album_id")
    photos = [_photo(p, f"photos[{i}]") for i, p in enumerate(data["photos"])]
    seen = [p.uuid for p in photos]
    if len(set(seen)) != len(seen):
        _fail("photos", "a photo id repeats")
    originals = [p.original_path for p in photos]
    if len(set(originals)) != len(originals):
        _fail("photos", "two photos name the same original")
    removed_raw = data.get("removed_photo_ids", [])
    if not isinstance(removed_raw, list):
        _fail("removed_photo_ids", "must be a list")
    removed = frozenset(_uuid(r, "removed_photo_ids") for r in removed_raw)
    if removed & set(seen):
        _fail("removed_photo_ids", "a photo cannot be both live and removed")
    return Index(album_uuid, data["revision"], sha256, data["processing"]["inventory_complete"], tuple(photos), removed)


def check_successor(index: Index, *, revision: int, sha256: str, live: set[uuid.UUID]) -> bool:
    """Whether ``index`` may replace the published one; False means "same snapshot, nothing to do".

    Raises when it is older, a different snapshot at the same revision, or silently drops photos the
    album already shows -- an incomplete scan must never look like a deletion.
    """
    if index.revision < revision:
        _fail("revision", f"older than the published revision {revision}")
    if index.revision == revision:
        if index.sha256 == sha256:
            return False
        _fail("revision", f"a different index is already published at revision {revision}")
    if not index.inventory_complete and index.removed & live:
        _fail("removed_photo_ids", "an incomplete scan cannot remove published photos")
    missing = live - {p.uuid for p in index.photos} - index.removed
    if missing:
        _fail("photos", f"{len(missing)} photo(s) missing without being listed in removed_photo_ids")
    return True


# The example offered next to the album form; a test checks that it passes ``parse``.
SAMPLE = json.dumps(
    {
        "schema_version": SCHEMA_VERSION,
        "album_id": "c00f63ce-2872-4a27-9640-de9dcb16def5",
        "revision": 1,
        "generated_at": "2026-10-26T06:00:00Z",
        "producer": {"name": "SportPhotoIndexer", "version": "0.1.0"},
        "bib_normalization": "trim-nfc-exact-v1",
        "processing": {"inventory_complete": True, "complete": True, "total": 1, "processed": 1},
        "photos": [
            {
                "id": "2a318e91-ae62-4bba-9f7f-274dc90b69b4",
                "original": {
                    "path": "IMG_0001.jpg",
                    "sha256": "0" * 64,
                    "bytes": 2500000,
                    "media_type": "image/jpeg",
                },
                "processing_state": "processed",
                "bibs": [{"value": "120", "state": "accepted", "method": "manual", "content_sha256": "0" * 64}],
            }
        ],
        "removed_photo_ids": [],
    },
    indent=2,
)
