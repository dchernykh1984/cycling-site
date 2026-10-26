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


@dataclass
class Result:
    # (registration id, bib) -> (state, device_id, client_revision)
    assignments: dict[tuple[int, str], tuple[str, str, int]]
    warnings: list[str]


def _collect(uploads, valid_ids: set[int], warnings: list[str]):
    """(registration, bib) -> (device, revision, line number), and the bibs of lines without the field."""
    pairs: dict[tuple[int, str], tuple[str, int, int]] = {}
    unreferenced: set[str] = set()
    lines = ((device_id, revision, item) for device_id, revision, items in uploads for item in items)
    for line_no, (device_id, revision, item) in enumerate(lines):
        line, warning = parse_line(item, max_stages=settings.START_LIST_MAX_STAGES)
        if warning:
            warnings.append(warning)
        if not line.refs_present:
            unreferenced.update(line.bibs)
            continue
        for reg in line.refs:
            if reg not in valid_ids:
                warnings.append(f"r{reg}: not a registration of this event")
                continue
            for bib in line.bibs:
                if len(pairs) >= _MAX_ASSIGNMENTS:
                    warnings.append("too many assignments; the rest are ignored")
                    return pairs, unreferenced
                pairs.setdefault((reg, bib), (device_id, revision, line_no))
    return pairs, unreferenced


def compute(uploads, valid_ids: set[int], previous: dict[tuple[int, str], str]) -> Result:
    """Every assignment the uploaded lines make, worked out in memory before anything is written.

    ``uploads``: (device_id, client_revision, items). ``previous``: the current (registration, bib)
    -> state, used only to keep a binding whose line lost its field in an older program.
    """
    warnings: list[str] = []
    pairs, unreferenced_bibs = _collect(uploads, valid_ids, warnings)
    # Conflicts: one registration on two lines with different bibs, or one bib on two lines.
    lines_by_reg: dict[int, set[int]] = {}
    lines_by_bib: dict[str, set[int]] = {}
    for (reg, bib), (_, _, ln) in pairs.items():
        lines_by_reg.setdefault(reg, set()).add(ln)
        lines_by_bib.setdefault(bib, set()).add(ln)
    assignments = {}
    for (reg, bib), (device, revision, _) in pairs.items():
        conflict = len(lines_by_reg[reg]) > 1 or len(lines_by_bib[bib]) > 1
        assignments[(reg, bib)] = ("conflict" if conflict else "active", device, revision)
    # A bib bound before whose line now comes without the field keeps its binding, for review.
    for (reg, bib), _state in previous.items():
        if (reg, bib) not in assignments and bib in unreferenced_bibs:
            assignments[(reg, bib)] = ("review", "", 0)
    return Result(assignments, warnings)


def recompute(competition) -> list[str]:
    """Replace the competition's IssuedBib rows from its stored start lists; returns the warnings.

    Call inside the start-list upload's transaction, under its competition lock.
    """
    from event_photos.models import IssuedBib, IssuedBibEvent
    from protocols.models import StartListUpload
    from registrations.models import CompetitionRegistration

    uploads = [
        (u.device_id, u.client_revision, u.items) for u in StartListUpload.objects.filter(competition=competition)
    ]
    valid = set(
        CompetitionRegistration.objects.filter(competition=competition, is_rejected=False).values_list("pk", flat=True)
    )
    current = {(b.registration_id, b.bib): b for b in IssuedBib.objects.filter(competition=competition)}
    result = compute(uploads, valid, {k: v.state for k, v in current.items()})
    events = []
    with transaction.atomic():
        for key, row in current.items():
            if key not in result.assignments:
                events.append(
                    IssuedBibEvent(competition=competition, registration_id=key[0], bib=key[1], change="withdrawn")
                )
                row.delete()
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
            elif existing.state == state:
                continue
            else:
                existing.state = state
                existing.save(update_fields=["state", "updated_at"])
            change = "assigned" if state == "active" else state
            events.append(
                IssuedBibEvent(
                    competition=competition,
                    registration_id=reg,
                    bib=bib,
                    change=change,
                    device_id=device,
                    client_revision=revision,
                )
            )
        IssuedBibEvent.objects.bulk_create(events)
    return result.warnings
