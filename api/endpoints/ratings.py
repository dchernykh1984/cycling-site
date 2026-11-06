"""Ratings (issue #436), as the site's pages give them: a member rates an event they took part in, or
refuses to, once; nothing keeps who wrote a review.

The answers follow the review form (``ratings.form``): a score by question key -- ``overall`` from 1 to 5,
required -- and the text ones, ``comment``.
"""

import datetime
from http import HTTPStatus

from django.shortcuts import get_object_or_404
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from api.auth import member_auth
from calendar_app.models import Competition
from ratings import form, rules

router = Router(tags=["ratings"])


class PendingOut(Schema):
    competition_id: int
    title: str
    last_day: datetime.date


class ReviewIn(Schema):
    answers: dict[str, int | str]  # by question key: "overall" (1-5), "comment"


@router.get("/pending", response=list[PendingOut], auth=member_auth, summary="The events I took part in and may rate")
def pending(request):
    return [PendingOut(competition_id=c.pk, title=c.title, last_day=c.last_day) for c in rules.reviewable(request.auth)]


@router.post(
    "/events/{competition_id}/review",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Rate an event I took part in; nothing keeps that the review is mine",
)
def review(request, competition_id: int, payload: ReviewIn):
    competition = get_object_or_404(Competition, pk=competition_id)
    answers, errors = form.clean(payload.answers)
    if errors:
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "; ".join(f"{key}: {text}" for key, text in errors.items()))
    if not rules.answer(request.auth, competition, answers):
        raise HttpError(HTTPStatus.CONFLICT, "You may not rate this event, or you have answered already")
    return Status(HTTPStatus.NO_CONTENT, None)


@router.post(
    "/events/{competition_id}/decline",
    response={HTTPStatus.NO_CONTENT: None},
    auth=member_auth,
    summary="Refuse to rate an event I took part in; final, as a review is",
)
def decline(request, competition_id: int):
    competition = get_object_or_404(Competition, pk=competition_id)
    if not rules.answer(request.auth, competition):
        raise HttpError(HTTPStatus.CONFLICT, "You may not rate this event, or you have answered already")
    return Status(HTTPStatus.NO_CONTENT, None)
