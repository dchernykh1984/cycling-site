"""An event's protocol sections (issue #452): which there are, what each is called, what each holds.

The first section is every event's and is called "Protocols" until the organizer names it; the others
the organizer adds, named in every language, and the timing software publishes into one by its number.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max
from django.utils.translation import gettext, gettext_lazy, override

from calendar_app.models import Competition

from .models import Protocol, ProtocolSection

FIRST = 1
# The largest number a section can have: the column's own range.
LAST = 2_147_483_647


class SectionRefusedError(Exception):
    """What was asked of a section cannot be done; the message says why, in the language it is read in."""


def exists(competition: Competition, number: int) -> bool:
    """Whether the timing software may publish into section ``number`` of the event."""
    if number == FIRST:
        return True
    return ProtocolSection.objects.filter(competition=competition, number=number, is_deleted=False).exists()


def _named(competition: Competition) -> dict[int, ProtocolSection]:
    return {s.number: s for s in ProtocolSection.objects.filter(competition=competition, is_deleted=False)}


def _name(named: dict[int, ProtocolSection], number: int) -> str:
    return named[number].name if number in named else gettext("Protocols")


def shown(competition: Competition) -> list[dict]:
    """The sections that hold protocols, in their order, each with its name and its protocols."""
    named = _named(competition)
    held: dict[int, list[Protocol]] = {}
    for protocol in competition.protocols.order_by("section", "pk"):
        held.setdefault(protocol.section, []).append(protocol)
    return [
        {"number": number, "name": _name(named, number), "protocols": protocols} for number, protocols in held.items()
    ]


def name_of(protocol: Protocol) -> str | None:
    """The name of the section a protocol is shown in, when the organizer gave it one."""
    section = ProtocolSection.objects.filter(
        competition_id=protocol.competition_id, number=protocol.section, is_deleted=False
    ).first()
    return section.name if section else None


def names(section: ProtocolSection | None) -> dict[str, str]:
    """A section's name in every language; for the first section without a name, the one it is shown under."""
    result = {}
    for code, _language in settings.LANGUAGES:
        if section is not None:
            result[code] = getattr(section, f"name_{code}") or ""
        else:
            with override(code):
                result[code] = gettext("Protocols")
    return result


def listing(competition: Competition) -> list[dict]:
    """Every section the organizer looks after, the first always, with its names and its protocols' count."""
    named = _named(competition)
    counts = dict(Protocol.objects.filter(competition=competition).values_list("section").annotate(count=Count("pk")))
    return [
        {
            "number": number,
            "is_first": number == FIRST,
            "name": _name(named, number),
            "names": names(named.get(number)),
            "protocols": counts.get(number, 0),
        }
        for number in sorted({FIRST, *named})
    ]


def _lock(competition: Competition) -> None:
    # Uploads take turns on the event's row too, so a section is never deleted under a protocol landing in it.
    Competition.objects.select_for_update().get(pk=competition.pk)


def _set_names(section: ProtocolSection, given: dict[str, str]) -> None:
    for code, _language in settings.LANGUAGES:
        setattr(section, f"name_{code}", given[code])


def add(competition: Competition, given: dict[str, str]) -> ProtocolSection:
    """A new section numbered after every section the event ever had, so no number is given twice."""
    with transaction.atomic():
        _lock(competition)
        last = ProtocolSection.objects.filter(competition=competition).aggregate(last=Max("number"))["last"]
        section = ProtocolSection(competition=competition, number=max(last or FIRST, FIRST) + 1)
        _set_names(section, given)
        section.save()
        return section


def rename(competition: Competition, number: int, given: dict[str, str]) -> ProtocolSection:
    """Give a section new names; the first section gets its row the first time it is named."""
    with transaction.atomic():
        _lock(competition)
        section = ProtocolSection.objects.filter(competition=competition, number=number, is_deleted=False).first()
        if section is None:
            if number != FIRST:
                raise ProtocolSection.DoesNotExist
            section = ProtocolSection(competition=competition, number=FIRST)
        _set_names(section, given)
        section.save()
        return section


def delete(competition: Competition, number: int) -> None:
    """Delete an empty section; its number is not given again."""
    with transaction.atomic():
        _lock(competition)
        if number == FIRST:
            raise SectionRefusedError(gettext_lazy("The first section cannot be deleted."))
        section = ProtocolSection.objects.filter(competition=competition, number=number, is_deleted=False).first()
        if section is None:
            raise ProtocolSection.DoesNotExist
        if Protocol.objects.filter(competition=competition, section=number).exists():
            raise SectionRefusedError(
                gettext_lazy("The section still holds protocols: delete them in the protocol generator first.")
            )
        section.is_deleted = True
        section.save(update_fields=["is_deleted"])
