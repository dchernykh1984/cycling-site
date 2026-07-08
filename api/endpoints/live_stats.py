"""Live per-competitor race stats for the Garmin Connect IQ data field.

FinishProtocolGenerator (authenticated by the competition ``upload_token``) POSTs a full snapshot
mapping each competitor's bib to an opaque ``string -> string`` dict of stats (place, gaps, laps,
...). The site stores it verbatim -- it neither parses nor hardcodes the individual keys, so new
stats can be added later with no site change -- and serves one bib's dict via a public GET for an
approved, visible competition. The Garmin field polls that GET by competition id + bib.
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from ninja import Router, Schema
from ninja.errors import HttpError

from calendar_app.models import Competition
from protocols.models import CompetitionLiveStats

router = Router(tags=["live-stats"])

# Kept under Django's DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB default), like the timing endpoints.
_MAX_BODY_BYTES = 2_000_000
_MAX_COMPETITORS = 20000
_MAX_KEYS_PER_COMPETITOR = 50
_MAX_BIB_LEN = 64
_MAX_KEY_LEN = 64
_MAX_VALUE_LEN = 256


# -- Schemas ---------------------------------------------------------------


class LiveStatsIn(Schema):
    competition_token: str
    # bib -> {key: value}; values are strings so the "dumb" watch just maps key -> text.
    stats: dict[str, dict[str, str]]


class LiveStatsUploadOut(Schema):
    count: int
    updated_at: datetime


class LiveStatsOut(Schema):
    competition_id: int
    bib: str
    stats: dict[str, str]
    updated_at: datetime


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


def _validate_stats(request, stats: dict[str, dict[str, str]]) -> None:
    if len(request.body) > _MAX_BODY_BYTES:
        raise HttpError(400, f"Payload is too large (max {_MAX_BODY_BYTES} bytes)")
    if len(stats) > _MAX_COMPETITORS:
        raise HttpError(400, f"Too many competitors (max {_MAX_COMPETITORS})")
    for bib, values in stats.items():
        if len(bib) > _MAX_BIB_LEN:
            raise HttpError(400, f"A bib is too long (max {_MAX_BIB_LEN} characters)")
        if len(values) > _MAX_KEYS_PER_COMPETITOR:
            raise HttpError(400, f"Too many keys for one competitor (max {_MAX_KEYS_PER_COMPETITOR})")
        for key, value in values.items():
            if len(key) > _MAX_KEY_LEN:
                raise HttpError(400, f"A key is too long (max {_MAX_KEY_LEN} characters)")
            if len(value) > _MAX_VALUE_LEN:
                raise HttpError(400, f"A value is too long (max {_MAX_VALUE_LEN} characters)")


# -- Endpoints -------------------------------------------------------------


@router.post("/", response=LiveStatsUploadOut, auth=None, summary="Upload the live per-competitor stats snapshot")
def upload_live_stats(request, payload: LiveStatsIn):
    competition = _competition_by_token(payload.competition_token)
    stats = payload.stats or {}
    _validate_stats(request, stats)
    obj, _ = CompetitionLiveStats.objects.update_or_create(competition=competition, defaults={"data": stats})
    return {"count": len(stats), "updated_at": obj.updated_at}


@router.get("/{int:competition_id}/{bib}", response=LiveStatsOut, auth=None, summary="Get one competitor's live stats")
def get_live_stats(request, competition_id: int, bib: str):
    try:
        competition = Competition.objects.get(
            pk=competition_id,
            status=Competition.Status.APPROVED,
            is_deleted=False,
            is_hidden=False,
        )
    except Competition.DoesNotExist:
        raise HttpError(404, "Not found") from None
    try:
        live = competition.live_stats
    except CompetitionLiveStats.DoesNotExist:
        raise HttpError(404, "Not found") from None
    bib_stats = live.data.get(bib)
    if bib_stats is None:
        raise HttpError(404, "Not found")
    return {"competition_id": competition.pk, "bib": bib, "stats": bib_stats, "updated_at": live.updated_at}
