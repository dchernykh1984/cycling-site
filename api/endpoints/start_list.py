"""Start-list exchange API for the offline-referee desktop tools.

StartProtocolMaker pushes the registered-at-start list (per `device_id`) for a competition;
FinishProtocolGenerator fetches every device's list and merges them into one start protocol.
Both authenticate with the competition's `upload_token` (the same token the protocol-upload
endpoint uses), so the endpoints are unauthenticated otherwise.
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from calendar_app.models import Competition
from protocols.models import StartListUpload

router = Router(tags=["start-list"])

_MAX_ITEMS = 20000
_MAX_ITEM_LEN = 2000
_MAX_DEVICE_ID_LEN = 64
# Reject when the actual request body exceeds this, kept well under Django's
# DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB default) so any payload the app accepts is never rejected by
# Django (or the reverse proxy) before this handler runs. Measuring the real serialized body
# (request.body) is exact for any content -- a char-count estimate under-counts non-BMP chars,
# which json.dumps(ensure_ascii=True) escapes to a 12-byte surrogate pair (\uXXXX\uXXXX).
_MAX_BODY_BYTES = 2_000_000


class StartListIn(Schema):
    competition_token: str
    device_id: str
    items: list[str] = Field(default_factory=list)
    client_revision: int = Field(
        ge=1,
        le=2**63 - 1,  # bounded to PostgreSQL bigint to avoid a 500
        description=(
            "Required strictly-increasing per-device counter. The stored list is replaced only by a "
            "strictly-newer revision; an older revision -- or a different snapshot at the same "
            "revision -- is rejected with 409, while an identical re-send at the same revision is a "
            "no-op. A client that lost its counter reads the device's current revision from GET and "
            "resumes from there."
        ),
    )


class StartListUploadOut(Schema):
    device_id: str
    count: int
    client_revision: int  # the revision now stored for this device (echoed for confirmation/recovery)


class StartListDeviceOut(Schema):
    device_id: str
    items: list[str]
    client_revision: int  # this device's current revision; resume from here after losing local state
    updated_at: datetime


class StartListOut(Schema):
    devices: list[StartListDeviceOut]
    items: list[str]  # every device's items concatenated, in device-id order (convenience)


def _competition_by_token(token: str) -> Competition:
    try:
        return Competition.objects.get(
            upload_token=token,
            status=Competition.Status.APPROVED,
            is_deleted=False,
        )
    except (Competition.DoesNotExist, ValidationError):
        raise HttpError(401, "Invalid competition_token") from None


@router.post("/", response=StartListUploadOut, auth=None, summary="Upload a device's start list")
def upload_start_list(request, payload: StartListIn):
    """Upsert one device's start list for a competition (compare-and-set on `client_revision`).

    The stored list is replaced only by a strictly-newer revision. An older revision, or a
    *different* snapshot at the same revision, is rejected with **409** (an identical re-send at the
    same revision is a no-op). The accepted revision is returned, and GET exposes each device's
    current revision, so a client that lost its local counter can resume from the server's value.
    """
    competition = _competition_by_token(payload.competition_token)

    device_id = (payload.device_id or "").strip()
    if not device_id:
        raise HttpError(400, "device_id is required")
    if len(device_id) > _MAX_DEVICE_ID_LEN:
        raise HttpError(400, f"device_id too long (max {_MAX_DEVICE_ID_LEN})")

    if len(request.body) > _MAX_BODY_BYTES:
        raise HttpError(400, f"Start list is too large (max {_MAX_BODY_BYTES} bytes)")

    items = payload.items or []
    if len(items) > _MAX_ITEMS:
        raise HttpError(400, f"Too many items (max {_MAX_ITEMS})")
    if any(len(item) > _MAX_ITEM_LEN for item in items):
        raise HttpError(400, f"An item is too long (max {_MAX_ITEM_LEN} characters)")

    revision = payload.client_revision
    # Atomic compare-and-set: lock the device's row, then reject a stale (older) snapshot and a
    # conflicting one at the same revision; only a strictly-newer revision (or an identical re-send
    # at the same revision) replaces the items. The lock serializes concurrent uploads for the same
    # device, and the GET reads a consistent MVCC snapshot, so a concurrent fetch never sees a
    # partially-written list.
    with transaction.atomic():
        # Lock the competition row first: an empty queryset locks nothing, so two concurrent first
        # uploads for the same device would both pass `existing is None` and collide on the unique
        # constraint (IntegrityError/500, possibly leaving the older snapshot). Locking a row that
        # always exists serializes them, so the second sees the row created by the first.
        Competition.objects.select_for_update().get(pk=competition.pk)
        existing = (
            StartListUpload.objects.select_for_update().filter(competition=competition, device_id=device_id).first()
        )
        if existing is not None:
            # Include the stored revision in the 409s so a client that lost its counter can recover
            # without a separate GET.
            if revision < existing.client_revision:
                raise HttpError(409, f"A newer start list (revision {existing.client_revision}) is already stored")
            if revision == existing.client_revision:
                if items != existing.items:
                    raise HttpError(
                        409, f"A different start list is already stored at revision {existing.client_revision}"
                    )
                # Identical re-send (e.g. a network retry): a true no-op, so `updated_at` does not
                # move and a consumer polling it isn't misled into seeing a new snapshot.
                return {
                    "device_id": device_id,
                    "count": len(existing.items),
                    "client_revision": existing.client_revision,
                }
            existing.items = items
            existing.client_revision = revision
            existing.save(update_fields=["items", "client_revision", "updated_at"])
        else:
            StartListUpload.objects.create(
                competition=competition, device_id=device_id, items=items, client_revision=revision
            )
    return {"device_id": device_id, "count": len(items), "client_revision": revision}


@router.get("/", response=StartListOut, auth=None, summary="Get all devices' start lists")
def get_start_list(request, competition_token: str):
    """Return every device's start list for a competition plus a merged convenience list."""
    competition = _competition_by_token(competition_token)
    uploads = list(StartListUpload.objects.filter(competition=competition).order_by("device_id"))
    devices = [
        {"device_id": u.device_id, "items": u.items, "client_revision": u.client_revision, "updated_at": u.updated_at}
        for u in uploads
    ]
    merged = [line for u in uploads for line in u.items]
    return {"devices": devices, "items": merged}
