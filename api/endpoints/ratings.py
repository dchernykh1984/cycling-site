"""Ratings (issue #436), as the site's pages give them: a member rates an event they took part in, or
refuses to, once; nothing keeps who wrote a review.

The answers follow the review form (``ratings.form``): a score by question key -- ``overall`` from 1 to 5,
required -- and the text ones, ``comment``.
"""

import datetime
from http import HTTPStatus

from django.shortcuts import get_object_or_404
from django.utils import translation
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from api.auth import member_auth
from assistant import llm
from calendar_app.models import Competition
from calendar_app.visibility import can_manage_or_own
from ratings import digest, form, rules, scores

router = Router(tags=["ratings"])


class PendingOut(Schema):
    competition_id: int
    title: str
    last_day: datetime.date


class ReviewIn(Schema):
    answers: dict[str, int | str]  # by question key: "overall" (1-5), "comment"


@router.get(
    "/pending",
    response=list[PendingOut],
    auth=member_auth,
    summary="The events I, or people without an account I added, took part in and I may rate",
)
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


class OwnDigestOut(Schema):
    competition_id: int
    title: str
    last_day: datetime.date
    reviews: int
    digest_reviews: int | None  # how many reviews the digest in the language was written from; None: not written


@router.get(
    "/mine",
    response=list[OwnDigestOut],
    auth=member_auth,
    summary="The events I posted with reviews enough for a digest, the latest first",
)
def mine(request, language: str = ""):
    """``language`` -- ru, kk or en -- picks the titles and the digest; the request's otherwise."""
    with translation.override(language or translation.get_language()):
        return [
            OwnDigestOut(
                competition_id=row["competition"].pk,
                title=row["competition"].title,
                last_day=row["competition"].last_day,
                reviews=row["reviews"],
                digest_reviews=row["written"],
            )
            for row in digest.of_author(request.auth)
        ]


class OrganizerOut(Schema):
    user_id: int
    name: str
    average: float  # of the overall scores, from 1 to 5
    reviews: int
    events: int


@router.get(
    "/organizers", response=list[OrganizerOut], auth=None, summary="The organizers rated by their events' participants"
)
def organizers(request):
    """The best first; an organizer shows from ``ratings.scores.PUBLIC_FROM`` scores."""
    return [
        OrganizerOut(
            user_id=row["organizer"].pk,
            name=row["organizer"].public_display_name,
            average=round(row["average"], 2),
            reviews=row["reviews"],
            events=row["events"],
        )
        for row in scores.organizers()
    ]


class SummaryOut(Schema):
    reviews: int
    average: float | None  # from digest.DIGEST_FROM reviews up, as the spread and the digest
    spread: dict[int, int] | None  # score -> how many gave it
    digest: str | None
    digest_reviews: int | None  # how many reviews the digest was written from


def _edited(request, competition_id: int):
    competition = get_object_or_404(Competition, pk=competition_id)
    if not can_manage_or_own(request.auth, competition):
        raise HttpError(HTTPStatus.FORBIDDEN, "Only the people who edit the event see what its participants think")
    return competition


def _summary_out(competition) -> SummaryOut:
    figures = digest.figures(competition)
    kept = digest.kept(competition) if figures["shown"] else None
    return SummaryOut(
        reviews=figures["reviews"],
        average=round(figures["average"], 2) if figures["shown"] else None,
        spread=dict(figures["spread"]) if figures["shown"] else None,
        digest=kept.text if kept else None,
        digest_reviews=kept.reviews if kept else None,
    )


@router.get(
    "/events/{competition_id}/summary",
    response=SummaryOut,
    auth=member_auth,
    summary="What the participants think of an event (who edits it)",
)
def summary(request, competition_id: int, language: str = ""):
    """``language`` -- ru, kk or en -- picks the digest's language; the request's otherwise."""
    competition = _edited(request, competition_id)
    with translation.override(language or translation.get_language()):
        return _summary_out(competition)


@router.post(
    "/events/{competition_id}/summary",
    response=SummaryOut,
    auth=member_auth,
    summary="Write the digest of an event's reviews, again once more came (who edits it)",
)
def write_summary(request, competition_id: int, language: str = ""):
    competition = _edited(request, competition_id)
    with translation.override(language or translation.get_language()):
        try:
            digest.write(competition)
        except ValueError:
            raise HttpError(HTTPStatus.CONFLICT, "Too few reviews for a digest") from None
        except llm.UnavailableError:
            raise HttpError(
                HTTPStatus.SERVICE_UNAVAILABLE, "The language model did not answer; try again later"
            ) from None
        return _summary_out(competition)
