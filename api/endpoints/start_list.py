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


class StartListIn(Schema):
    competition_token: str
    device_id: str
    items: list[str] = Field(default_factory=list)
    # Monotonic per-device revision (the sender's epoch-ms). A snapshot older than the stored one
    # is rejected so a delayed/reordered request can't roll the device's list back. 0 = legacy.
    client_revision: int = 0


class StartListUploadOut(Schema):
    device_id: str
    count: int


class StartListDeviceOut(Schema):
    device_id: str
    items: list[str]
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
    """Upsert one device's start list for a competition. Re-posting the same `device_id`
    overwrites the previously stored items."""
    competition = _competition_by_token(payload.competition_token)

    device_id = (payload.device_id or "").strip()
    if not device_id:
        raise HttpError(400, "device_id is required")
    if len(device_id) > _MAX_DEVICE_ID_LEN:
        raise HttpError(400, f"device_id too long (max {_MAX_DEVICE_ID_LEN})")

    items = payload.items or []
    if len(items) > _MAX_ITEMS:
        raise HttpError(400, f"Too many items (max {_MAX_ITEMS})")
    if any(len(item) > _MAX_ITEM_LEN for item in items):
        raise HttpError(400, f"An item is too long (max {_MAX_ITEM_LEN} characters)")

    revision = payload.client_revision or 0
    # Atomic compare-and-set: lock the device's row, reject a stale (older-revision) snapshot, and
    # otherwise replace the items wholesale. The lock serializes concurrent uploads for the same
    # device so a late request can't overwrite a newer one; the GET reads a consistent MVCC
    # snapshot, so a concurrent fetch never sees a partially-written list.
    with transaction.atomic():
        existing = (
            StartListUpload.objects.select_for_update().filter(competition=competition, device_id=device_id).first()
        )
        if existing is not None and revision < existing.client_revision:
            raise HttpError(409, "A newer start list is already stored for this device_id")
        if existing is None:
            StartListUpload.objects.create(
                competition=competition, device_id=device_id, items=items, client_revision=revision
            )
        else:
            existing.items = items
            existing.client_revision = revision
            existing.save(update_fields=["items", "client_revision", "updated_at"])
    return {"device_id": device_id, "count": len(items)}


@router.get("/", response=StartListOut, auth=None, summary="Get all devices' start lists")
def get_start_list(request, competition_token: str):
    """Return every device's start list for a competition plus a merged convenience list."""
    competition = _competition_by_token(competition_token)
    uploads = list(StartListUpload.objects.filter(competition=competition).order_by("device_id"))
    devices = [{"device_id": u.device_id, "items": u.items, "updated_at": u.updated_at} for u in uploads]
    merged = [line for u in uploads for line in u.items]
    return {"devices": devices, "items": merged}
