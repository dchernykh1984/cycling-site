"""Organizers' ratings (issue #436): the average of the overall scores the participants of their events gave.

An organizer is the member who posted the event. A rating is shown from PUBLIC_FROM scores, so that one
review does not make or break it. What counts: reviews of approved events that are neither hidden nor
deleted, posted by a member -- not by the account the site's own agents post through.
"""

from django.db.models import Avg, Count, FloatField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

from accounts.models import User
from calendar_app.models import Competition
from ratings import form
from ratings.models import Review

#: How many scores an organizer's rating needs before it is shown
PUBLIC_FROM = 3


def counted():
    """The reviews that count towards their organizer's rating, with a score to count."""
    return Review.objects.filter(
        answers__has_key=form.RATED,
        competition__status=Competition.Status.APPROVED,
        competition__is_deleted=False,
        competition__is_hidden=False,
        competition__submitted_by__isnull=False,
        competition__submitted_by__is_service_account=False,
    )


def _by_organizer(reviews):
    return (
        reviews.values("competition__submitted_by")
        .annotate(
            reviews=Count("id"),
            events=Count("competition", distinct=True),
            average=Avg(Cast(KeyTextTransform(form.RATED, "answers"), FloatField())),
        )
        .filter(reviews__gte=PUBLIC_FROM)
    )


def organizers() -> list[dict]:
    """The organizers with a rating to show, the best first: organizer, average, reviews, events."""
    rows = list(_by_organizer(counted()).order_by("-average", "-reviews", "competition__submitted_by"))
    people = User.objects.in_bulk([row["competition__submitted_by"] for row in rows])
    return [
        {
            "organizer": people[row["competition__submitted_by"]],
            "average": row["average"],
            "reviews": row["reviews"],
            "events": row["events"],
        }
        for row in rows
    ]


def of_organizer(user) -> dict | None:
    """``user``'s rating as an organizer -- average, reviews, events -- or None while it is not shown."""
    if user is None or user.is_service_account:
        return None
    row = _by_organizer(counted().filter(competition__submitted_by=user)).order_by("competition__submitted_by").first()
    return {"average": row["average"], "reviews": row["reviews"], "events": row["events"]} if row else None
