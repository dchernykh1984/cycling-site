"""A virtual race with protocols (specs/495-virtual-race).

A group race may belong to an event. Its riders are the event's registered riders, each with a bib -- the one the
event gave their registration, else the first free one in their category's range -- riding their category's laps.
The site writes the race's timing into the event's timing streams as one more device: the start list
(StartProtocolMaker's lines), the groups' start times and every crossing of the start-finish line and of the control
points (the chronometer's lines), so FinishProtocolGenerator's "Get data from site" reads it with the event's token
as it reads chronometers. The token never leaves the server, and the race writes only while the event has one.
"""

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from accounts import roles
from calendar_app.models import Competition
from calendar_app.visibility import is_public
from event_photos.bindings import recompute as recompute_bindings
from event_photos.models import IssuedBib
from protocols.models import FinishTimesUpload, GroupTimesUpload, RemotePointUpload, StartListUpload
from registrations.models import CompetitionRegistration, RegistrationCategory
from trainer.models import GroupRide, GroupRideMember

#: A route's control points beyond the start-finish line (point 0): its turns back, a few at most
MAX_POINTS = 20
#: A crossing may come this much after it happened (a page catching up) and no later than now plus this
CLOCK_SLACK = timedelta(seconds=5)
_EPOCH = datetime(1970, 1, 1).date()


class NoBibError(Exception):
    """The rider's category has no free bib left."""


def device_id(race) -> str:
    return f"virtual-race-{race.pk}"


def can_tie(user, competition: Competition) -> bool:
    """An event's own organizer ties a race to it, an admin to any; the event public -- every member's lobby names it
    on the race's card -- and not over."""
    if not is_public(competition):
        return False
    if (competition.date_end or competition.date_start) < timezone.localdate():
        return False
    if roles.at_least(user, roles.MANAGE_ALL_EVENTS):
        return True
    return competition.submitted_by_id == user.pk and roles.at_least(user, roles.PUBLISH_EVENTS)


def _registrations_of(user):
    """The rider's own registrations that were not rejected: the ones a race with protocols takes."""
    return CompetitionRegistration.objects.filter(user=user, is_rejected=False)


def registration_of(user, competition: Competition) -> CompetitionRegistration | None:
    """The rider's own registration for the event that was not rejected."""
    return (
        _registrations_of(user)
        .filter(competition=competition)
        .select_related("category", "team")
        .order_by("registered_at", "pk")
        .first()
    )


def registered_for(user, event_ids) -> set[int]:
    """Which of these events the rider holds a registration for, as registration_of finds one: in one query."""
    if not event_ids:
        return set()
    return set(_registrations_of(user).filter(competition_id__in=event_ids).values_list("competition_id", flat=True))


def writing(race) -> bool:
    """Whether the race writes timing: tied to an event that is live and keeps its upload token."""
    event = race.competition
    return bool(event and event.upload_token and not event.is_deleted and event.status == Competition.Status.APPROVED)


# -- Bibs, groups and starts ------------------------------------------------


def _taken(competition: Competition) -> set[str]:
    """Every bib the event has given: by its start lists and by its virtual races, those kept for riders who left."""
    issued = IssuedBib.objects.filter(competition=competition, state=IssuedBib.State.ACTIVE).values_list(
        "bib", flat=True
    )
    riding = (
        GroupRideMember.objects.filter(group__competition=competition).exclude(bib="").values_list("bib", flat=True)
    )
    kept = {
        bib
        for bibs in GroupRide.objects.filter(competition=competition).values_list("kept_bibs", flat=True)
        for bib in bibs.values()
    }
    return set(issued) | set(riding) | kept


def assign_bib(member) -> str:
    """The member's bib: theirs already, the one the event gave their registration, the one they had before they left
    the race, else the first free one in their category's range (from 1 when it has none). Called with the race's row
    locked, so two joins never share one."""
    if member.bib:
        return member.bib
    registration = member.registration
    given = (
        IssuedBib.objects.filter(
            competition=registration.competition, registration=registration, state=IssuedBib.State.ACTIVE
        )
        .order_by("pk")
        .values_list("bib", flat=True)
        .first()
    )
    if given:
        return given
    kept = member.group.kept_bibs.get(str(registration.pk))
    others = IssuedBib.objects.filter(competition=registration.competition, bib=kept, state=IssuedBib.State.ACTIVE)
    if kept and not others.exclude(registration=registration).exists():
        return kept
    category = registration.category
    low = category.bib_from if category and category.bib_from else 1
    high = category.bib_to if category and category.bib_to else None
    taken = _taken(registration.competition)
    bib = low
    while str(bib) in taken:
        bib += 1
    if high is not None and bib > high:
        raise NoBibError
    return str(bib)


def categories(competition: Competition) -> list[RegistrationCategory]:
    return list(competition.registration_categories.filter(is_deleted=False).order_by("order", "pk"))


def group_of(member) -> str:
    """The rider's group as the start list and the group times name it: their category, else one group for all."""
    category = member.registration.category if member.registration else None
    return _one_line(category.name) if category else "1"


def laps_of(member) -> int:
    """The category's laps on a loop (one when it has none); a route that is not a loop is ridden once."""
    if not member.group.loop:
        return 1
    category = member.registration.category if member.registration else None
    return category.laps if category and category.laps else 1


def _order(race) -> list:
    """The race's riders in start order: in a race with protocols those with bibs, by category, then bib; in one
    without, in the order they joined."""
    if race.competition_id is None:
        return list(race.memberships.select_related("user").order_by("joined_at", "pk"))
    index = {c.pk: i for i, c in enumerate(categories(race.competition))}

    def key(m):
        category_id = m.registration.category_id if m.registration else None
        bib = m.bib
        return (index.get(category_id, len(index)), int(bib) if bib.isdecimal() else 10**9, bib)

    # a rider whose registration is gone or was rejected is no longer on the start list, their bib still theirs
    riders = (
        race.memberships.exclude(bib="")
        .filter(registration__isnull=False, registration__is_rejected=False)
        .select_related("registration", "registration__category", "user")
    )
    return sorted(riders, key=key)


def start_offset_s(race, member) -> int:
    """Seconds after the race's start the rider starts: their own place in the start order times the interval in a
    time trial, their category's place times the gap in a group race with protocols."""
    if race.mode == race.Mode.ITT:
        order = [m.pk for m in _order(race)]
        return order.index(member.pk) * race.itt_interval_s if member.pk in order else 0
    if not race.competition or not member.bib:
        return 0
    index = {c.pk: i for i, c in enumerate(categories(race.competition))}
    category_id = member.registration.category_id if member.registration else None
    return index.get(category_id, 0) * race.group_gap_s if category_id is not None else 0


# -- Lines ------------------------------------------------------------------


def _one_line(text: str) -> str:
    return " ".join(str(text).replace("#", " ").split())


def clock(when: datetime, zone) -> str:
    """'D H:M:S.mmm' as the chronometer writes a moment: D the days since 1970 at the event's place."""
    local = timezone.localtime(when, zone)
    days = (local.date() - _EPOCH).days
    return f"{days} {local.hour}:{local.minute}:{local.second}.{local.microsecond // 1000:03d}"


def _delay(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def start_line(race, member) -> str:
    """StartProtocolMaker's line: bib#name#group#laps#stages#year#team#city#comment#start delay#r<registration>#"""
    r = member.registration
    name = _one_line(f"{r.last_name or member.user.last_name} {r.first_name or member.user.first_name}")
    team = _one_line(r.team.name) if r.team else ""
    delay = _delay(start_offset_s(race, member)) if race.mode == race.Mode.ITT else ""
    fields = [member.bib, name, group_of(member), str(laps_of(member)), "1", str(r.birth_date.year), team]
    return "#".join([*fields, _one_line(r.city), "", delay, f"r{r.pk}"]) + "#"


# -- The event's timing streams ---------------------------------------------


def _stream(model, race, **key):
    row, _created = model.objects.select_for_update().get_or_create(
        competition=race.competition, device_id=device_id(race), **key
    )
    return row


def _replace(row, items: list[str]) -> None:
    if row.items != items:
        row.items = items
        row.client_revision += 1
        row.save(update_fields=["items", "client_revision", "updated_at"])


def last_start(race, riders) -> datetime:
    """The last rider's own start: the race's in a mass start, later by the categories' gaps or the trial's
    intervals."""
    if not riders:
        return race.start_at
    if race.mode == race.Mode.ITT:
        return race.start_at + timedelta(seconds=(len(riders) - 1) * race.itt_interval_s)
    return race.start_at + timedelta(seconds=max(start_offset_s(race, m) for m in riders))


def write_start(race) -> None:
    """When the race's last rider starts, for the lobby to list it until then, and in a race with protocols its start
    list and its groups' start times, as they stand: called whenever a rider joins or leaves."""
    with transaction.atomic():
        # one writer at a time, the riders read once it is this one's turn: two riders joining at once each write
        # the list with both of them, whichever writes last
        GroupRide.objects.select_for_update().filter(pk=race.pk).first()
        riders = _order(race)
        race.last_start_at = last_start(race, riders)
        race.save(update_fields=["last_start_at"])
        if race.competition is None or not writing(race):
            return
        zone = race.competition.timezone
        _replace(_stream(StartListUpload, race), [start_line(race, m) for m in riders])
        starts: dict[str, datetime] = {}
        for m in riders:
            group = group_of(m)
            if group not in starts:
                offset = 0 if race.mode == race.Mode.ITT else start_offset_s(race, m)
                starts[group] = race.start_at + timedelta(seconds=offset)
        _replace(_stream(GroupTimesUpload, race), [f"{g}#{clock(t, zone)}#" for g, t in starts.items()])
    recompute_bindings(race.competition)


def record_crossing(race, member, point: int, at: datetime, last: bool) -> bool:
    """One crossing of point 0 (the start-finish line) or a control point, written once; False when it is not the
    race's to write -- no token, no bib, a point out of range, a moment before the rider's start or ahead of now, or
    more crossings of the point than the rider has laps: a page sends one a lap, so a stream never grows past them."""
    if not writing(race) or not member.bib or not 0 <= point <= MAX_POINTS:
        return False
    if member.registration is None or member.registration.is_rejected:  # off the start list: FPG would not know them
        return False
    start = race.start_at + timedelta(seconds=start_offset_s(race, member))
    if at < start - CLOCK_SLACK or at > timezone.now() + CLOCK_SLACK:
        return False
    line = f"{member.bib}#{clock(at, race.competition.timezone)}#{'finish' if last and point == 0 else 'nextLap'}#"
    with transaction.atomic():
        row = _stream(FinishTimesUpload, race) if point == 0 else _stream(RemotePointUpload, race, point_number=point)
        if line in row.items:
            return True
        if sum(item.startswith(f"{member.bib}#") for item in row.items) >= laps_of(member):
            return False
        _replace(row, [*row.items, line])
    return True
