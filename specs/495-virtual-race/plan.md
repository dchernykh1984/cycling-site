# Implementation Plan: A virtual race with protocols

**Branch**: `virtual-ride-routes-guide` (pull request #495) | **Spec**: [spec.md](spec.md)

## Summary

A group race (`trainer.GroupRide`) may belong to an event (`calendar_app.Competition`). Its members carry their
registration and bib (`trainer.GroupRideMember`). The site writes the race's timing into the event's existing timing
streams (`protocols.StartListUpload`, `GroupTimesUpload`, `FinishTimesUpload`, `RemotePointUpload`) as one more
device, so FinishProtocolGenerator's "Get data from site" reads it as it reads chronometers; the bib binding the
start list makes (`event_photos.bindings`) follows from the same stream. The page finds the route's control points,
counts its rider's laps, reports crossings with the presence it already sends every second, draws bibs on the kit,
and drafts by the race's rules.

## Constitution Check

- **IV (languages)**: the page's new words in `text/{ru,kk,en}.js`; the API's refusals in the catalogues.
- **VI (anywhere)**: nothing about a place or a sport: categories, laps, bib ranges and time zones are the event's.
- **VII (API)**: making, joining and riding a race are API operations (`/api/v1/virtual-ride/`), tested.
- **VIII (one fact, one home)**: laps and bib ranges stay the category's; the bib is the member's, and the start
  list stream says it to the rest of the site as StartProtocolMaker's does.
- **X (checked, private)**: the token stays on the server; crossings are bounded and checked against the route and
  the rider's start; only the event's organizer or an admin ties a race to it.
- **XI (API promises)**: new optional fields only.

## Data model

- `GroupRide`: `competition` (FK, null, SET_NULL), `mode` (`group`/`itt`), `group_gap_s`, `itt_interval_s`,
  `draft_between_groups` (bool, default true).
- `GroupRideMember`: `registration` (FK, null, SET_NULL), `bib` (char, blank), `crossings` written (so a retry is
  written once -- kept in the stream itself: a line already there is not appended again).

## Design

1. `trainer/race.py`: `can_tie(user, event)`, `assign_bib(member, registration)` under a row lock on the race,
   `start_offset(member)`, `write_start_list(race)`, `write_group_times(race)`, `record(member, crossing)`; the
   time format and the device id; nothing written when the event has no token.
2. API: `GroupIn` gains the race's fields; `GroupOut` names the event and, for the asking member, their bib,
   category, laps and start offset; `RiderOut` a rider's bib, category and drag area; `PresenceIn` a rider's drag
   area and the crossings since the last answer. A join without a registration is a 403 with the reason and link.
3. Page: control points from the route (a turn back: the road's way reversing within 60 m); laps from the member's
   category; a time trial's own start; crossings sent until the site answers; `wakeOf` by mode, category and drag
   areas; a bib plate on each rider's back; the phone notice for a heavy route.
4. Tests: `tests/test_virtual_race.py` (making, joining, bibs, streams, token, retries);
   `tests/e2e/test_virtual_race.py` (control points, laps, drafting rules, the bib on the kit, the phone notice).
