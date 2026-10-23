"""The gallery's public event choices and the facts shown alongside a linked album."""

import re

from anyascii import anyascii
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from calendar_app.models import Competition
from locations.models import Location, LocationProposal

RESULT_LIMIT = 20


def public_events():
    return Competition.objects.filter(
        status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False, invite_only=False
    ).order_by("-date_start", "pk")


def search_words(value):
    """One script and case for matching, including a mixture of Cyrillic and Latin letters."""
    return re.findall(r"[a-z0-9]+", anyascii(value).casefold())


def matching_ids(query):
    events = public_events()
    words = search_words(query)
    if not words:
        return list(events.values_list("pk", flat=True)[: RESULT_LIMIT + 1])
    matches = []
    # Stream just the names and date; only the matching choices load their relations. This keeps
    # the form and the response bounded without a database extension or a second stored index.
    rows = events.values_list("pk", "title_ru", "title_kk", "title_en", "date_start").iterator(chunk_size=200)
    for pk, ru, kk, en, day in rows:
        text = " ".join(search_words(" ".join((ru or "", kk or "", en or "", day.isoformat()))))
        if all(word in text for word in words):
            matches.append(pk)
            if len(matches) > RESULT_LIMIT:
                break
    return matches


def describe_events(queryset):
    """Serialize short facts, with the same locale and visibility on the form and public album."""
    events = list(queryset.select_related("location").prefetch_related("event_types", "disciplines__category"))
    paths = {
        event.location.path[:end]
        for event in events
        if event.location_id
        for end in range(Location.steplen, len(event.location.path) + 1, Location.steplen)
    }
    locations = {
        node.path: node
        for node in Location.objects.filter(path__in=paths, is_deleted=False, is_hidden=False).exclude(
            proposal__status=LocationProposal.Status.PENDING_APPROVAL
        )
    }
    result = []
    for event in events:
        disciplines = list(event.disciplines.all())
        dates = date_format(event.date_start, "SHORT_DATE_FORMAT")
        if event.date_end and event.date_end != event.date_start:
            dates += " - " + date_format(event.date_end, "SHORT_DATE_FORMAT")
        place = ", ".join(
            locations[path].name
            for path in sorted(locations)
            if event.location_id and event.location.path.startswith(path)
        )
        facts = (
            (_("Dates"), dates),
            (_("Location"), place),
            (_("Event types"), ", ".join(kind.name for kind in event.event_types.all())),
            (_("Direction"), ", ".join(dict.fromkeys(discipline.category.name for discipline in disciplines))),
            (_("Disciplines"), ", ".join(discipline.name for discipline in disciplines)),
        )
        result.append(
            {
                "id": event.pk,
                "title": event.title,
                "titles": {language: getattr(event, f"title_{language}") or "" for language in ("ru", "kk", "en")},
                "date": event.date_start.isoformat(),
                "url": event.get_absolute_url(),
                "details": [{"label": label, "value": value} for label, value in facts if value],
            }
        )
    return result
