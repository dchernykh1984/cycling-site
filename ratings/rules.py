"""Who may review an event, and the answer they give (issue #436).

A member reviews an event they took part in: their own entry, a bib the start list gave it, and that bib
in the event's protocol data as having started -- a result, or any mark but "dns". A person without an
account has none to answer with -- a child, or one who never signed up -- so the member who added and
entered them answers instead: once for the event, however many of them started, weighing as one
participant. The protocol data is what the timing programs send beside the HTML; an event with HTML alone
asks nobody. They are asked from the day after the event's last day by its own place's calendar -- not on
the day, in the heat of it -- until they review or refuse, once. An organizer who took part in their own
event reviews it as anyone else; nobody reviews one the site's agents posted.
"""

import datetime

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Prefetch, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts import virtual_members
from calendar_app.models import Competition
from event_photos.index import normalize_bib
from event_photos.models import IssuedBib
from locations.models import timezone_of
from ratings import form
from ratings.models import Review, ReviewMark
from registrations.models import CompetitionRegistration

#: A protocol row's mark for a rider who did not start
NOT_STARTED = "dns"
#: How long the bibs read from an event's protocols are kept: they are read again once a protocol changes
STARTED_KEPT_SECONDS = 24 * 60 * 60
#: How many events the banner asks about at a time; the rest wait their turn, none is dropped
ASKED_AT_ONCE = 2


def ended(competition) -> bool:
    """Whether the event's last day is over where it took place."""
    return timezone.now().astimezone(timezone_of(competition.location)).date() > competition.last_day


def started_bibs(competition) -> set[str]:
    """The bibs the event's protocol data lists as having started. The banner asks on every page, so they
    are kept until a protocol of the event changes, comes or goes, rather than read from its documents
    each time."""
    documents = competition.protocols.exclude(document__isnull=True)
    state = documents.aggregate(latest=Max("last_updated"), count=Count("id"))
    if state["latest"] is None:
        return set()
    key = f"ratings:started:{competition.pk}:{state['count']}:{state['latest'].timestamp()}"
    kept = cache.get(key)
    if kept is not None:
        return kept
    bibs: set[str] = set()
    for document in documents.values_list("document", flat=True):
        _collect(document, bibs)
    cache.set(key, bibs, STARTED_KEPT_SECONDS)
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
    """The events ``user`` took part in, or the people without an account they added did, and may still
    review, the latest first -- the one remembered best; only ``competition`` when it is given."""
    if not getattr(user, "is_authenticated", False):
        return []
    # No place on Earth is a day ahead of UTC and more: an event whose last day comes after today there
    # is over nowhere yet, and is left out before any time zone is worked out
    latest_over = datetime.datetime.now(datetime.UTC).date()
    entries = (
        CompetitionRegistration.objects.filter(
            Q(user=user) | Q(virtual_member__in=virtual_members.of(user)),
            is_rejected=False,
            issued_bibs__state=IssuedBib.State.ACTIVE,
            competition__status=Competition.Status.APPROVED,
            competition__is_deleted=False,
            competition__is_hidden=False,
            competition__submitted_by__isnull=False,
        )
        .exclude(competition__submitted_by__is_service_account=True)
        .exclude(competition__review_marks__user=user)
        .annotate(last_day=Coalesce("competition__date_end", "competition__date_start"))
        .filter(last_day__lte=latest_over)
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
    return sorted(found.values(), key=lambda event: (event.last_day, event.pk), reverse=True)


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
