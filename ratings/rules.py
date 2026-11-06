"""Who may review an event, and the answer they give (issue #436).

A member reviews an event they took part in: their own entry, a bib the start list gave it, and that bib
in the event's protocol data as having started -- a result, or any mark but "dns". The protocol data is
what the timing programs send beside the HTML; an event with HTML alone asks nobody. They are asked from
the day after the event's last day by its own place's calendar -- not on the day, in the heat of it --
until they review or refuse, once. Nobody reviews their own event, nor one the site's agents posted.
"""

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from calendar_app.models import Competition
from event_photos.index import normalize_bib
from event_photos.models import IssuedBib
from locations.models import timezone_of
from ratings import form
from ratings.models import Review, ReviewMark
from registrations.models import CompetitionRegistration

#: A protocol row's mark for a rider who did not start
NOT_STARTED = "dns"


def ended(competition) -> bool:
    """Whether the event's last day is over where it took place."""
    return timezone.now().astimezone(timezone_of(competition.location)).date() > competition.last_day


def started_bibs(competition) -> set[str]:
    """The bibs the event's protocol data lists as having started."""
    bibs: set[str] = set()
    for document in competition.protocols.exclude(document__isnull=True).values_list("document", flat=True):
        _collect(document, bibs)
    return bibs


def _collect(part: dict, bibs: set[str]) -> None:
    for section in part.get("sections") or []:
        column = next((c.get("id") for c in section.get("columns") or [] if c.get("role") == "bib"), None)
        for row in section.get("rows") or [] if column else []:
            if str(row.get("status") or "").strip().lower() == NOT_STARTED:
                continue
            cell = (row.get("cells") or {}).get(column)
            text = cell.get("text") if isinstance(cell, dict) else cell
            if text:
                bibs.add(normalize_bib(str(text)))
        _collect(section, bibs)


def reviewable(user, competition=None) -> list:
    """The events ``user`` took part in and may still review, the earliest first; only ``competition``
    when it is given."""
    if not getattr(user, "is_authenticated", False):
        return []
    entries = (
        CompetitionRegistration.objects.filter(
            user=user,
            is_rejected=False,
            issued_bibs__state=IssuedBib.State.ACTIVE,
            competition__status=Competition.Status.APPROVED,
            competition__is_deleted=False,
            competition__is_hidden=False,
            competition__submitted_by__isnull=False,
        )
        .exclude(competition__submitted_by=user)
        .exclude(competition__submitted_by__is_service_account=True)
        .exclude(competition__review_marks__user=user)
        .select_related("competition", "competition__location")
        .prefetch_related(
            Prefetch("issued_bibs", queryset=IssuedBib.objects.filter(state=IssuedBib.State.ACTIVE), to_attr="bibs")
        )
        .distinct()
    )
    if competition is not None:
        entries = entries.filter(competition=competition)
    found: dict[int, Competition] = {}
    started: dict[int, set[str]] = {}
    for entry in entries:
        event = entry.competition
        if event.pk in found or not ended(event):
            continue
        if event.pk not in started:
            started[event.pk] = started_bibs(event)
        if {normalize_bib(bib.bib) for bib in entry.bibs} & started[event.pk]:
            found[event.pk] = event
    return sorted(found.values(), key=lambda event: (event.last_day, event.pk))


def answer(user, competition, answers: dict | None = None) -> bool:
    """``user`` answers the request to review ``competition``: a review with ``answers``, a refusal
    without. False when they may not review it, or answered it already."""
    if not reviewable(user, competition):
        return False
    try:
        with transaction.atomic():
            ReviewMark.objects.create(user=user, competition=competition)
            if answers is not None:
                Review.objects.create(competition=competition, form=form.VERSION, answers=answers)
    except IntegrityError:  # answered at the same moment from another tab
        return False
    return True
