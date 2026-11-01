from datetime import date
from http import HTTPStatus
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from ninja import Router, Schema
from ninja.errors import HttpError

from calendar_app.models import Competition
from registrations.models import counted

router = Router(tags=["participants"])

# The bib numbers a category without a range of its own covers in the timing tools.
_ALL_BIBS = (1, 20000)


# -- Schemas ---------------------------------------------------------------


class CategoryOut(Schema):
    id: int
    name: str
    male: bool
    female: bool
    birth_from: date | None
    birth_to: date | None
    laps: int | None
    bib_from: int
    bib_to: int


class ParticipantOut(Schema):
    id: int
    first_name: str
    last_name: str
    participant_names: str
    participant_birth_years: str
    participant_cities: str
    birth_date: date
    birth_year: int
    gender: str
    category_id: int | None
    category_name: str
    team: str
    city: str
    additional_info: str
    is_approved: bool
    is_paid: bool


class ParticipantsResponseOut(Schema):
    competition_id: int
    competition_title: str
    birth_date_mode: str
    registration_mode: str
    require_approval: bool
    require_payment: bool
    categories: list[CategoryOut]
    participants: list[ParticipantOut]


# -- Endpoint --------------------------------------------------------------


@router.get("/", response=ParticipantsResponseOut, auth=None, summary="Get participants by competition token")
def get_participants(request, competition_token: str, include_unpaid: bool = False):
    """
    Returns the participant list for a competition identified by its upload/competition token.
    This endpoint is used by StartProtocolMaker to fetch registered participants.

    Where the competition requires payment, people who have signed up but not paid are left out
    unless ``include_unpaid`` asks for them. A client that asks has to tell them apart itself:
    each participant carries ``is_paid`` and the competition carries ``require_payment``.
    """
    try:
        competition = Competition.objects.get(upload_token=competition_token)
    except (Competition.DoesNotExist, ValidationError):
        raise HttpError(HTTPStatus.UNAUTHORIZED, "invalid competition_token") from None

    if competition.status != Competition.Status.APPROVED or competition.is_deleted:
        raise HttpError(HTTPStatus.UNAUTHORIZED, "competition not found or not approved")

    # Unpaid entries used to be dropped here outright, which left a referee at the start line
    # unable to see that part of the entry list was outstanding. Widening it is opt-in rather
    # than the new default because a client that does not ask for them cannot tell them apart:
    # every copy of the timing tools already in the field would list unpaid riders as if they
    # had paid, which is worse than not listing them at all.
    qs = counted(competition, paid_only=not include_unpaid).select_related("category", "team")

    participant_list = list(qs)
    # Return every active group (category) of the competition, not only those a participant is
    # registered in, so the offline timing tools can sync the full group list even before anyone has
    # signed up for a group. Soft-deleted categories are excluded (like the rest of the app) -- except
    # ones a returned participant is still registered in, so their group name is not lost. Ordered
    # deterministically (by bib range, then name) for a stable dropdown.
    referenced_category_ids = {r.category_id for r in participant_list if r.category_id}
    categories = competition.registration_categories.filter(
        Q(is_deleted=False) | Q(pk__in=referenced_category_ids)
    ).order_by("bib_from", "name", "id")

    def _participant(r) -> dict[str, Any]:
        return {
            "id": r.pk,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "participant_names": r.participant_names or f"{r.last_name} {r.first_name}".strip(),
            "participant_birth_years": r.participant_birth_years or str(r.birth_date.year),
            "participant_cities": r.participant_cities or r.city,
            "birth_date": r.birth_date,
            "birth_year": r.birth_date.year,
            "gender": r.gender,
            "category_id": r.category_id,
            "category_name": r.category.name if r.category else "",
            "team": r.team.name if r.team else "",
            "city": r.city,
            "additional_info": r.additional_info,
            "is_approved": r.is_approved,
            "is_paid": r.is_paid,
        }

    return {
        "competition_id": competition.pk,
        "competition_title": competition.title,
        "birth_date_mode": competition.birth_date_mode,
        "registration_mode": competition.registration_mode,
        "require_approval": competition.require_approval,
        "require_payment": competition.require_payment,
        "categories": [
            {
                "id": c.pk,
                "name": c.name,
                "male": c.male,
                "female": c.female,
                "birth_from": c.birth_from,
                "birth_to": c.birth_to,
                "laps": c.laps,
                "bib_from": c.bib_from if c.bib_from is not None else _ALL_BIBS[0],
                "bib_to": c.bib_to if c.bib_to is not None else _ALL_BIBS[1],
            }
            for c in categories
        ],
        "participants": [_participant(r) for r in participant_list],
    }
