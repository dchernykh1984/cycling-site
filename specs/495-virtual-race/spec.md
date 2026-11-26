# Feature Specification: A virtual race with protocols

**Feature Branch**: `virtual-ride-routes-guide` (pull request #495, asked there)
**Created**: 2026-11-26
**Status**: Draft, implemented in the same pull request at the maintainer's word: "implement it in this pull
request, before its review cycles if possible"
**Input**: The maintainer, 2026-11-26: a "race" feature for the virtual ride -- laps from the registration, riders
registered through the event's form, bibs given automatically and worn on the riders' kit, the timing splits, the
start protocol and the groups' start times made by themselves; FinishProtocolGenerator, run by the maintainer,
makes the protocols from them with the event's token. Checkpoints at the start, the finish (one line on a loop) and
every turn back, smooth ones included (Al-Farabi at the turn by Vostochka on Granfondo 2026). Two modes: a group
race and an individual time trial without drafting; the wind and the other conditions are the race maker's; in a
group race the maker says whether riders of different categories draft each other. Drafting should depend on whom
a rider hides behind -- a small rider on a TT bike or a big one on an MTB. A heavy route may lag on a phone: the
phone is told so, and a route is lightened only without losing quality.

## Decisions taken (the maintainer's answers, 2026-11-26)

- **Bibs** are given when a registered rider joins the race: the first free number in their category's range
  (`bib_from` to `bib_to`), or from 1 when the category has none; a bib the event already gave the registration
  (a start list from StartProtocolMaker) is kept.
- **Only riders registered for the event** (a registration not rejected) may join; anyone else is told to register
  first, with the event's registration link.
- **The race is made in the virtual ride**, where a group race is gathered: its maker picks one of their own events
  (an organizer's own, any for an admin). Its groups, laps and bib ranges come from the event's registration.
- **The timing is written by the site itself** into the event's timing streams -- the token never reaches a
  rider's browser -- and only while the event has its upload token: a regenerated token changes nothing for the
  race (FinishProtocolGenerator reads with the new one), a deleted one stops the writing, and the race never makes
  a token.

## User Scenarios & Testing

### User Story 1 - An organizer makes a race for their event (Priority: P1)

1. **Given** an organizer on the virtual ride page, **When** they gather a group race, **Then** they may tie it to
   one of their own events that is public (approved, neither hidden nor invite-only) and not over, and set: the mode (a group race or an individual time
   trial), the gap between the groups' starts in a group race (0: one mass start), the interval between riders in a
   time trial, whether riders of different categories draft each other in a group race, and the wind.
2. **Given** a race tied to an event, **Then** its card names the event and links to it; the API carries the same.
3. **Given** someone who is neither the event's organizer nor an admin, **Then** they cannot tie a race to it.

### User Story 2 - A registered rider joins and gets a bib (Priority: P1)

1. **Given** a rider registered for the event (not rejected), **When** they join the race, **Then** they get a bib:
   the one the event gave their registration, else the first free one in their category's range; the bib stays
   theirs if they leave and join again.
2. **Given** a rider without a registration, **Then** joining is refused with the reason and the event's link.
3. **Given** two riders joining at once, **Then** they never get the same bib.

### User Story 3 - The race runs by itself (Priority: P1)

1. **Given** a group race, **Then** each category (group) starts at the race's start plus its place in the
   categories' order times the gap; a time trial starts each rider their place times the interval after the
   race's start, in the order of categories, then bibs.
2. **Given** a rider's category, **Then** on a loop they ride its laps (one when it has none) and finish after the
   last; a route that is not a loop is ridden once, and the start list says one lap.
3. **Given** a loop, **Then** the start and finish are one line (point 0); every turn back on the route -- the road
   reversing its way within a short stretch -- is a control point (1..N, in the route's order).
4. **Given** a time trial, **Then** no rider drafts another; **given** a group race whose maker said no drafting
   between categories, **Then** a rider drafts only riders of their own category.
5. **Given** any ride with others, **Then** the wake a rider takes depends on the rider ahead: a bigger drag area
   ahead shelters more, a smaller less.

### User Story 4 - FinishProtocolGenerator gets the race's timing (Priority: P1)

1. **Given** a race tied to an event with a token, **Then** the event's timing streams carry, as the device
   `virtual-race-<id>`: the start list (a line per rider with a bib), the groups' start times, every crossing of
   point 0 (`nextLap`, the last `finish`) and of each control point; FinishProtocolGenerator's "Get data from site"
   reads them with the event's token and makes the protocols as from chronometers.
2. **Given** the event's token deleted, **Then** the race writes nothing more; **given** it regenerated, **Then**
   the race goes on writing and FinishProtocolGenerator reads with the new token.
3. **Given** a crossing sent twice (a retry), **Then** it is written once.

### User Story 5 - A rider wears their bib (Priority: P2)

1. **Given** a race with protocols, **Then** each rider's kit carries their bib on the back, the rider's own too.

### User Story 6 - A phone is told a heavy route may lag (Priority: P2)

1. **Given** a route with a large scenery (Granfondo 2026) on a phone, **Then** the setup says it may run slowly on
   a phone; the route keeps its quality.

### Edge Cases

- A category's range used up: the rider gets no bib and joining is refused with the reason.
- A rider whose registration moves to another category after joining keeps the bib; their laps follow the category.
- A crossing before the rider's start or ahead of the site's clock, or of a point beyond the route's few (20 at
  most), is not written; the page reports none after the rider's last lap.
- A rider who goes back to the menu as they finish: the crossings not sent yet go from the menu with their race.
- A rider who starts late (a page may start up to 30 s after its start): each crossing is the moment it happened
  on the site's clock, as a chronometer takes it, so the time lost is theirs.
- A race whose event is deleted or loses its approval writes nothing.
- An out-and-back route (not a loop): point 0 is the start's line, the finish its last crossing; its turn is a point.

## Requirements

- **FR-001**: A group race may carry an event (`competition_id`), a mode (`group` or `itt`), a gap between groups
  (s), an interval between time-trial riders (s) and whether categories draft each other; only the event's
  organizer or an admin may tie it, and only to a public event that is not over: every member's lobby lists the
  race and names its event, and an event no longer public is not named there.
- **FR-002**: Joining a race with an event needs a registration for it that is not rejected; the member gets a bib
  as the decisions above say, kept across leaving and joining.
- **FR-003**: The race's start list, the groups' start times and the crossings go into the event's timing streams
  as the device `virtual-race-<id>`, in StartProtocolMaker's and the chronometer's line formats; only while the event
  has a token.
- **FR-004**: The page reports each crossing of point 0 and the control points with the moment it happened on the
  site's clock, until the site answers -- from the menu too; the site writes each once and only for a member with a
  bib.
- **FR-005**: The page ends a rider's race after their category's laps; a time trial starts each rider at their
  own time and takes no wake; a group race takes wakes across categories only when its maker allows it.
- **FR-006**: The wake a rider takes is the measured one (`DRAFT`) scaled by the square root of the drag areas
  ahead and behind, within 0.8 to 1.2 -- a model: the measurements say it grows with the leader's drag area, give
  no slope, and one study finds no effect.
- **FR-007**: A rider's bib is drawn on their kit; the page shows the race's event and each rider's bib.
- **FR-008**: On a phone (a coarse pointer) the start's summary says a route with many buildings and streets (more
  than 800 together: Granfondo 2026, the Medeu climb and the centre's loop have 1000 to 1400, the others under
  700) may run slowly.
- **FR-009**: Every operation is in the API (`/api/v1/virtual-ride/groups`, `/presence`) with its tests.

## Formats (what FinishProtocolGenerator reads)

- Start list: `bib#Last First#group#laps#1#year#team#city##start_delay#r<registration id>#` -- the group is the
  category's name; the start delay `H:MM:SS` in a time trial, empty otherwise.
- Group start: `group#D H:M:S.mmm#`; crossing: `bib#D H:M:S.mmm#nextLap#` or `...#finish#` -- D the days since
  1970 in the event's time zone, as the chronometer writes them.

## Success Criteria

- **SC-001**: A race with two categories and a time trial, run on a local site, gives FinishProtocolGenerator
  start lists, group times and crossings it reads without an error.
- **SC-002**: No rider's browser ever receives the event's token.
