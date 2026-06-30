"""Timing-data exchange API for the offline-referee desktop tools.

WindowsChronometer pushes its timing streams (group starts, finish-line crossings, and remote
control-point crossings) per ``device_id``; FinishProtocolGenerator fetches every device's stream
and merges them. Mirrors the start-list exchange (``api/endpoints/start_list.py``): the same
compare-and-set on ``client_revision``, the same ``competition_token`` (= ``upload_token``) auth,
and the same size guards. Three separate streams = three routers/models:

* ``/group-times/``   -> GroupTimesUpload   (one stream per device)
* ``/finish-times/``  -> FinishTimesUpload  (point 0; one stream per device)
* ``/remote-points/`` -> RemotePointUpload  (points 1..N; one stream per device & point_number)
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from calendar_app.models import Competition
from protocols.models import FinishTimesUpload, GroupTimesUpload, RemotePointUpload

group_times_router = Router(tags=["group-times"])
finish_times_router = Router(tags=["finish-times"])
remote_points_router = Router(tags=["remote-points"])

_MAX_ITEMS = 20000
_MAX_ITEM_LEN = 2000
_MAX_DEVICE_ID_LEN = 64
# Kept under Django's DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB default), like the start-list endpoint.
_MAX_BODY_BYTES = 2_000_000


# -- Schemas ---------------------------------------------------------------


class _TimingIn(Schema):
    competition_token: str
    device_id: str
    items: list[str] = Field(default_factory=list)
    client_revision: int = Field(
        ge=1,
        le=2**63 - 1,
        description=(
            "Required strictly-increasing per-device counter. The stored snapshot is replaced only "
            "by a strictly-newer revision; an older revision -- or a different snapshot at the same "
            "revision -- is rejected with 409, while an identical re-send at the same revision is a "
            "no-op. A client that lost its counter reads the current revision from GET."
        ),
    )


class RemoteTimingIn(_TimingIn):
    point_number: int = Field(ge=1, le=10_000, description="Remote control point number (1..N); point 0 is the finish.")


class TimingUploadOut(Schema):
    device_id: str
    count: int
    client_revision: int


class TimingDeviceOut(Schema):
    device_id: str
    items: list[str]
    client_revision: int
    updated_at: datetime


class TimingStreamOut(Schema):
    devices: list[TimingDeviceOut]
    items: list[str]  # every device's items concatenated, in device-id order (merged convenience)


class RemotePointOut(Schema):
    point_number: int
    devices: list[TimingDeviceOut]
    items: list[str]  # every device's items for this point, merged in device-id order


class RemotePointsOut(Schema):
    points: list[RemotePointOut]


# -- Helpers ---------------------------------------------------------------


def _competition_by_token(token: str) -> Competition:
    try:
        return Competition.objects.get(
            upload_token=token,
            status=Competition.Status.APPROVED,
            is_deleted=False,
        )
    except (Competition.DoesNotExist, ValidationError):
        raise HttpError(401, "Invalid competition_token") from None


def _validate_payload(request, device_id: str, items: list[str]) -> None:
    if not device_id:
        raise HttpError(400, "device_id is required")
    if len(device_id) > _MAX_DEVICE_ID_LEN:
        raise HttpError(400, f"device_id too long (max {_MAX_DEVICE_ID_LEN})")
    if len(request.body) > _MAX_BODY_BYTES:
        raise HttpError(400, f"Payload is too large (max {_MAX_BODY_BYTES} bytes)")
    if len(items) > _MAX_ITEMS:
        raise HttpError(400, f"Too many items (max {_MAX_ITEMS})")
    if any(len(item) > _MAX_ITEM_LEN for item in items):
        raise HttpError(400, f"An item is too long (max {_MAX_ITEM_LEN} characters)")


def _upsert(model, competition: Competition, device_id: str, revision: int, items: list[str], **key_extra) -> dict:
    """Compare-and-set upsert of one device's stream (optionally scoped by ``key_extra``).

    The stored snapshot is replaced only by a strictly-newer revision. An older revision, or a
    *different* snapshot at the same revision, is rejected with 409 (an identical re-send at the same
    revision is a no-op). Locking matches ``start_list.upload_start_list``: lock the competition row
    first so two concurrent first uploads for the same key can't both create and collide.
    """
    with transaction.atomic():
        Competition.objects.select_for_update().get(pk=competition.pk)
        existing = (
            model.objects.select_for_update().filter(competition=competition, device_id=device_id, **key_extra).first()
        )
        if existing is not None:
            if revision < existing.client_revision:
                raise HttpError(409, f"A newer snapshot (revision {existing.client_revision}) is already stored")
            if revision == existing.client_revision:
                if items != existing.items:
                    raise HttpError(
                        409, f"A different snapshot is already stored at revision {existing.client_revision}"
                    )
                return {
                    "device_id": device_id,
                    "count": len(existing.items),
                    "client_revision": existing.client_revision,
                }
            existing.items = items
            existing.client_revision = revision
            existing.save(update_fields=["items", "client_revision", "updated_at"])
        else:
            model.objects.create(
                competition=competition, device_id=device_id, items=items, client_revision=revision, **key_extra
            )
    return {"device_id": device_id, "count": len(items), "client_revision": revision}


def _stream_response(model, competition: Competition, **key_extra) -> dict:
    uploads = list(model.objects.filter(competition=competition, **key_extra).order_by("device_id"))
    devices = [
        {"device_id": u.device_id, "items": u.items, "client_revision": u.client_revision, "updated_at": u.updated_at}
        for u in uploads
    ]
    return {"devices": devices, "items": [line for u in uploads for line in u.items]}


# -- Group times -----------------------------------------------------------


@group_times_router.post("/", response=TimingUploadOut, auth=None, summary="Upload a device's group-start times")
def upload_group_times(request, payload: _TimingIn):
    competition = _competition_by_token(payload.competition_token)
    device_id = (payload.device_id or "").strip()
    items = payload.items or []
    _validate_payload(request, device_id, items)
    return _upsert(GroupTimesUpload, competition, device_id, payload.client_revision, items)


@group_times_router.get("/", response=TimingStreamOut, auth=None, summary="Get all devices' group-start times")
def get_group_times(request, competition_token: str):
    competition = _competition_by_token(competition_token)
    return _stream_response(GroupTimesUpload, competition)


# -- Finish times ----------------------------------------------------------


@finish_times_router.post("/", response=TimingUploadOut, auth=None, summary="Upload a device's finish times")
def upload_finish_times(request, payload: _TimingIn):
    competition = _competition_by_token(payload.competition_token)
    device_id = (payload.device_id or "").strip()
    items = payload.items or []
    _validate_payload(request, device_id, items)
    return _upsert(FinishTimesUpload, competition, device_id, payload.client_revision, items)


@finish_times_router.get("/", response=TimingStreamOut, auth=None, summary="Get all devices' finish times")
def get_finish_times(request, competition_token: str):
    competition = _competition_by_token(competition_token)
    return _stream_response(FinishTimesUpload, competition)


# -- Remote points ---------------------------------------------------------


@remote_points_router.post("/", response=TimingUploadOut, auth=None, summary="Upload a device's remote-point times")
def upload_remote_points(request, payload: RemoteTimingIn):
    competition = _competition_by_token(payload.competition_token)
    device_id = (payload.device_id or "").strip()
    items = payload.items or []
    _validate_payload(request, device_id, items)
    return _upsert(
        RemotePointUpload, competition, device_id, payload.client_revision, items, point_number=payload.point_number
    )


@remote_points_router.get(
    "/", response=RemotePointsOut, auth=None, summary="Get all remote points (each merged across devices)"
)
def get_remote_points(request, competition_token: str):
    """Return every remote point, each with its per-device snapshots and a merged item list.

    Lines for the same ``point_number`` from different devices are grouped into one point, so the
    generator gets one merged control-point stream per point regardless of how many machines timed it.
    """
    competition = _competition_by_token(competition_token)
    uploads = list(RemotePointUpload.objects.filter(competition=competition).order_by("point_number", "device_id"))
    points: dict[int, dict] = {}
    for u in uploads:
        point = points.setdefault(u.point_number, {"point_number": u.point_number, "devices": [], "items": []})
        point["devices"].append(
            {
                "device_id": u.device_id,
                "items": u.items,
                "client_revision": u.client_revision,
                "updated_at": u.updated_at,
            }
        )
        point["items"].extend(u.items)
    return {"points": [points[k] for k in sorted(points)]}
