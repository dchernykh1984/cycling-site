from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from ninja import Router, Schema
from ninja.errors import HttpError

from calendar_app.models import Competition

router = Router(tags=["participants"])


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
def get_participants(request, competition_token: str):
    """
    Returns the participant list for a competition identified by its upload/competition token.
    This endpoint is used by StartProtocolMaker to fetch registered participants.
    """
    try:
        competition = Competition.objects.get(upload_token=competition_token)
    except (Competition.DoesNotExist, ValidationError):
        raise HttpError(401, "invalid competition_token") from None

    if competition.status != Competition.Status.APPROVED or competition.is_deleted:
        raise HttpError(401, "competition not found or not approved")

    qs = competition.registrations.filter(is_rejected=False).select_related("category", "team")
    if competition.require_approval:
        qs = qs.filter(is_approved=True)
    if competition.require_payment:
        qs = qs.filter(is_paid=True)

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
                "bib_from": c.bib_from if c.bib_from is not None else 1,
                "bib_to": c.bib_to if c.bib_to is not None else 20000,
            }
            for c in categories
        ],
        "participants": [_participant(r) for r in participant_list],
    }
