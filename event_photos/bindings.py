"""Which registration got which bib, read from the start lists StartProtocolMaker sends.

A line is ``number#name#group#laps#stage#year#team#city#comment#time_shift#refs#`` (see
contracts/start-list-bindings.md). ``refs`` is field 10: comma-separated ``r<registration id>``
tokens. A writer that knows the field always writes it, even empty, so a line has at least 11 ``#``;
a line with 10 comes from an older StartProtocolMaker and its field is *absent*, not empty -- the
difference between "the referee unlinked it" and "an old program dropped it".
"""

import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

_TOKEN = re.compile(r"^r([0-9]{1,18})\Z")
_NOT_PAID = "NOT_PAID"
_MAX_BIB = 32
# The start list endpoint takes at most this many lines; stage bibs may not multiply past it.
_MAX_ASSIGNMENTS = 20000


@dataclass(frozen=True)
class Line:
    bibs: tuple[str, ...]
    refs: tuple[int, ...]
    refs_present: bool


def parse_line(line: str, *, max_stages: int) -> tuple[Line, str]:
    """The bibs and registration ids of one line, and a warning ("" if none)."""
    fields = line.split("#")
    refs_present = line.count("#") >= 11
    refs = []
    if refs_present:
        for token in fields[10].split(","):
            m = _TOKEN.match(token.strip())
            if m:  # an unknown kind of token is skipped, so a later kind cannot break this reader
                refs.append(int(m.group(1)))
    number = fields[0].strip()
    if not number or number == _NOT_PAID or len(number) > _MAX_BIB:
        return Line((), tuple(dict.fromkeys(refs)), refs_present), ""
    bibs = [number]
    warning = ""
    stage = fields[4].strip() if len(fields) > 4 else ""
    if stage.isdigit() and int(stage) > 1:
        n = int(stage)
        if not number.isdigit():
            warning = f"bib {number}: stages need a numeric bib"
        elif n > max_stages:
            warning = f"bib {number}: {n} stages is over the limit of {max_stages}"
        elif len(str(int(number) + n - 1)) > _MAX_BIB:
            warning = f"bib {number}: stage bibs too long"
        else:
            bibs = [str(int(number) + i) if i else number for i in range(n)]
    return Line(tuple(bibs), tuple(dict.fromkeys(refs)), refs_present), warning


class AssignmentOverflowError(Exception):
    pass


@dataclass
class Result:
    # (registration id, bib) -> (state, device_id, client_revision)
    assignments: dict[tuple[int, str], tuple[str, str, int]]
    warnings: list[str]


def _collect(uploads, valid_ids: set[int], warnings: list[str]):
    """(registration, bib) -> (device, revision, line number, restored).

    A binding from before whose line now comes without the field (edited in an older
    program) is restored here, ahead of the conflict check, so it can conflict like any
    other; one for a registration that is no longer valid is not restored.
    """
    pairs: dict[tuple[int, str], tuple[str, int, int, bool]] = {}
    unreferenced: dict[str, tuple[str, int, int]] = {}
    lines = ((device_id, revision, item) for device_id, revision, items in uploads for item in items)
    for line_no, (device_id, revision, item) in enumerate(lines):
        line, warning = parse_line(item, max_stages=settings.START_LIST_MAX_STAGES)
        if warning:
            warnings.append(warning)
        if not line.refs_present:
            for bib in line.bibs:
                unreferenced.setdefault(bib, (device_id, revision, line_no))
            continue
        for reg in line.refs:
            if reg not in valid_ids:
                warnings.append(f"r{reg}: not a registration of this event")
                continue
            for bib in line.bibs:
                pairs.setdefault((reg, bib), (device_id, revision, line_no, False))
        if len(pairs) > _MAX_ASSIGNMENTS:
            raise AssignmentOverflowError
    return pairs, unreferenced


def _restore(pairs, unreferenced, previous, valid_ids: set[int]) -> None:
    for reg, bib in previous:
        if (reg, bib) not in pairs and bib in unreferenced and reg in valid_ids:
            pairs[(reg, bib)] = (*unreferenced[bib], True)
    if len(pairs) > _MAX_ASSIGNMENTS:
        raise AssignmentOverflowError


def compute(uploads, valid_ids: set[int], previous) -> Result:
    """Every assignment the uploaded lines make, worked out in memory before anything is written.

    ``uploads``: (device_id, client_revision, items). ``previous``: the current
    (registration, bib) pairs. Raises AssignmentOverflowError rather than return a prefix.
    """
    warnings: list[str] = []
    pairs, unreferenced = _collect(uploads, valid_ids, warnings)
    _restore(pairs, unreferenced, previous, valid_ids)
    # Conflicts: one registration on two lines with different bibs, or one bib on two lines.
    lines_by_reg: dict[int, set[int]] = {}
    lines_by_bib: dict[str, set[int]] = {}
    for (reg, bib), (_, _, ln, _) in pairs.items():
        lines_by_reg.setdefault(reg, set()).add(ln)
        lines_by_bib.setdefault(bib, set()).add(ln)
    assignments = {}
    for (reg, bib), (device, revision, _, restored) in pairs.items():
        if len(lines_by_reg[reg]) > 1 or len(lines_by_bib[bib]) > 1:
            state = "conflict"
            warnings.append(f"bib {bib}: r{reg} is in conflict (device {device}, revision {revision})")
        else:
            state = "review" if restored else "active"
        assignments[(reg, bib)] = (state, device, revision)
    return Result(assignments, warnings)


def recompute(competition) -> list[str]:
    """Replace the competition's IssuedBib rows from its stored start lists; returns the warnings.

    Call inside the start-list upload's transaction, under its competition lock. On overflow the
    current bindings stay as they are. The warnings are kept for the event's organizer.
    """
    from event_photos.models import IssuedBib, IssuedBibEvent, StartListDiagnostics
    from protocols.models import StartListUpload
    from registrations.models import CompetitionRegistration

    uploads = [
        (u.device_id, u.client_revision, u.items) for u in StartListUpload.objects.filter(competition=competition)
    ]
    valid = set(
        CompetitionRegistration.objects.filter(competition=competition, is_rejected=False).values_list("pk", flat=True)
    )
    current = {(b.registration_id, b.bib): b for b in IssuedBib.objects.filter(competition=competition)}
    with transaction.atomic():
        try:
            result = compute(uploads, valid, set(current))
        except AssignmentOverflowError:
            warnings = [f"more than {_MAX_ASSIGNMENTS} bib assignments; the previous ones are kept"]
            _keep_diagnostics(StartListDiagnostics, competition, warnings)
            return warnings
        events = [
            IssuedBibEvent(competition=competition, registration_id=key[0], bib=key[1], change="withdrawn")
            for key in current
            if key not in result.assignments
        ]
        IssuedBib.objects.filter(
            pk__in=[row.pk for key, row in current.items() if key not in result.assignments]
        ).delete()
        for (reg, bib), (state, device, revision) in result.assignments.items():
            existing = current.get((reg, bib))
            if existing is None:
                IssuedBib.objects.create(
                    competition=competition,
                    registration_id=reg,
                    bib=bib,
                    state=state,
                    device_id=device,
                    client_revision=revision,
                )
            elif (existing.state, existing.device_id, existing.client_revision) == (state, device, revision):
                continue
            else:
                changed_state = existing.state != state
                existing.state, existing.device_id, existing.client_revision = state, device, revision
                existing.save(update_fields=["state", "device_id", "client_revision", "updated_at"])
                if not changed_state:
                    continue
            events.append(
                IssuedBibEvent(
                    competition=competition,
                    registration_id=reg,
                    bib=bib,
                    change="assigned" if state == "active" else state,
                    device_id=device,
                    client_revision=revision,
                )
            )
        IssuedBibEvent.objects.bulk_create(events)
        _keep_diagnostics(StartListDiagnostics, competition, result.warnings)
    return result.warnings


def _keep_diagnostics(model, competition, warnings: list[str]) -> None:
    model.objects.update_or_create(competition=competition, defaults={"warnings": warnings[:200]})
