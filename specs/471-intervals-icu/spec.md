# Feature Specification: Workouts from intervals.icu, rides sent where the member chooses, a truer ride

**Feature Branch**: `471-intervals-icu`
**Created**: 2026-11-19
**Status**: Phase 1 (services) in progress; phases 2 and 3 follow in their own pull requests
**Input**: Issue #471 asks the virtual ride to run the workouts planned in intervals.icu. It names
four things: syncing workouts from there, recording rides, a trainer simulator by power if there is
none, and a check that the virtual ride lacks no standard feature and gets its mechanics right. The
maintainer decided the points below in conversation on 2026-11-19; they are recorded here.

## Decisions (the maintainer, 2026-11-19)

1. **Services.**
   - Strava and intervals.icu each show on the profile whether they are connected.
   - A connected one also carries a box, "Send my rides to ...".
   - Members who have Strava connected today keep their rides going there: their box starts on.
   - intervals.icu starts with its box off.
2. **Connecting intervals.icu.** The member connects intervals.icu with their own API key, found
   under Settings, Developer Settings, on intervals.icu.
   - No OAuth application and no workout files to import.
   - The key is checked with intervals.icu when it is given, then kept encrypted. The site never
     shows it again, and the trainer page never receives it.
3. **Rides recorded.** A finished ride is saved on the site, as it is today, and sent to each
   service whose box is on.
4. **Workouts.** The trainer page lists the workouts planned in the member's intervals.icu calendar
   for today and the next seven days, and the rider picks one to ride.
   - FTP and zones stay in intervals.icu. A workout's targets are turned into watts with the FTP
     intervals.icu gives, and the site keeps none.
5. **The trainer by power.** A smart trainer is driven in one of two ways:
   - during a workout's power steps it holds the target watts (ERG), and the rider can switch ERG
     off;
   - otherwise, and outside workouts, it is set to the route's grade (SIM), so a climb gets harder,
     as today.
6. **The rider without a smart trainer keeps everything they have.** This covers plans by gear and
   cadence, speed and cadence sensors, and demo mode. A workout's power target is shown beside
   their estimated power.
7. **Mechanics.**
   - The air is thinner up high: its density follows the route's height.
   - Riding behind someone saves effort (drafting), behind bots and live riders alike. A smart
     trainer in SIM mode feels it too.
   - A rider with only a cadence sensor gets the hill's slowing in races and free rides by default.
     Plans by gear keep the speed of the gear, which is what they are built on.
8. **Three pull requests**, one per phase below, each with fifteen review cycles.

## User Scenarios & Testing

### User Story 1 - Services on the profile (Priority: P1, phase 1)

1. **Given** a member's profile, **Then** the "Virtual rides" card lists Strava and intervals.icu.
   - Each one says whether it is connected.
   - A connected one carries the box "Send my rides to <service>". Turning the box off keeps the
     connection and stops the sending.
   - Strava connections made before this change have the box on.
2. **Given** intervals.icu not connected, **Then** the card offers a field for the API key, says
   where intervals.icu shows it, and offers "Connect".
   - On "Connect" the key is checked with intervals.icu: the athlete it belongs to is asked for.
   - A refused key is reported with the reason, and nothing is kept.
   - An accepted key keeps the athlete's id and name, and the key encrypted.
3. **When** the member disconnects intervals.icu, or their account is deleted, **Then** the key and
   the connection are deleted.
4. **Given** a site without the encryption key setting, **Then** intervals.icu is not offered. This
   is how Strava is not offered without its application.
5. **Through the API**, a member reads their services and turns a box on or off. They also connect
   intervals.icu with a key and disconnect it (`/api/v1/virtual-ride/services/`).

### User Story 2 - Rides go to intervals.icu (Priority: P1, phase 1)

1. **Given** intervals.icu connected with its box on, **When** a ride is saved with its track and
   not in demo mode, **Then** it is uploaded to intervals.icu.
   - It goes as a TCX file named after its route, with the external id
     `universalbicycle-virtual-ride-<id>`.
   - The results say when the ride is on intervals.icu ("View on intervals.icu") or why it is not,
     and "Send again" retries.
2. **Given** Strava connected with its box off, **When** a ride is saved, **Then** it is not sent to
   Strava. "Send again" from the results still sends that one ride, at the member's own request.
3. **Given** the profile's recent rides, **Then** each links to its activity on every service that
   has it.
4. **Given** the member's key no longer accepted by intervals.icu, **Then** the next upload fails
   with the reason, and the connection is dropped so the member connects again. This is what
   happens to a Strava grant revoked at Strava.

### User Story 3 - Workouts from intervals.icu (Priority: P1, phase 2)

1. **Given** intervals.icu connected, **Then** the trainer page's plan screen lists the member's
   workouts planned in intervals.icu for today and the next seven days, with their date, name and
   duration. Only cycling workouts are listed.
2. **When** the rider picks one, **Then** its steps come from intervals.icu.
   - Power targets are in watts, from the FTP intervals.icu gives.
   - Ramps, repeats, free-ride steps, cadence targets and text cues are kept.
3. **During the ride**, the display shows the step's target and the next step.
   - The target is in watts, plus cadence where the workout sets it.
   - A power step on a smart trainer is held by ERG.
   - A switch turns ERG off: the trainer goes back to the grade, and the rider follows the target
     by feel.
4. **Without a smart trainer**, the target is shown beside the estimated power.
5. The ride is saved as a plan ride and goes to the services like any other ride. The site's own
   gear and cadence plans stay as they are.

### User Story 4 - A truer ride (Priority: P2, phase 3)

1. **Air density.** The air resisting the rider has the density of the route's height at that
   point, not one figure for every height.
2. **Drafting.** Close behind a rider ahead, bot or live member, the rider meets less air.
   - How much less follows published measurements: it shrinks with the gap and is gone a few
     lengths back.
   - A smart trainer in SIM mode is told the lighter drag.
3. **Cadence-only riders.** A rider with a cadence sensor only slows on climbs by default in races
   and free rides: their speed follows the physics from the trainer's power curve. A plan by gear
   keeps the speed of the gear.

### Edge Cases

- **The encryption key.** If the site's encryption key changes, or is lost, a stored intervals.icu
  key cannot be read. The connection then counts as gone, and the member connects again.
- **intervals.icu unavailable.** When intervals.icu cannot be reached or answers 429, the upload
  fails with the reason and can be sent again.
- **A workout without power steps** (heart rate or pace only) is listed but cannot be ridden by
  ERG. Its steps are shown as they are (phase 2).
- **A workout longer than a ride may last** is cut where the ride ends, as a ride's track already is.

## Requirements

- **FR-001**: Every operation has an API operation under `/api/v1/virtual-ride/`, for the session
  or a personal token. Connecting Strava stays a browser round trip.
- **FR-002**: The intervals.icu key is stored encrypted with the site's `INTEGRATIONS_ENCRYPTION_KEY`
  (Fernet). The API never returns it, no page shows it, and the trainer page never receives it.
- **FR-003**: One upload record per ride and service. A ride is sent automatically once, only while
  the service's box is on. "Send again" sends it at the member's request.
- **FR-004**: The privacy policy says what is kept for intervals.icu and what is sent there: the
  athlete's id and name, the key encrypted, and each ride sent.
- **FR-005**: FTP, zones and the workouts themselves stay in intervals.icu. The site keeps none of
  them (phase 2).
- **FR-006**: Nothing a rider without a smart trainer uses today is taken away.

## Key Entities

- `StravaConnection`, with `send_rides` added.
- `IntervalsConnection`: the member, the athlete id and name, the key encrypted, `send_rides`.
- `IntervalsUpload`: a ride, its status, the activity id and the error.

All three live in `trainer/models.py`.

## Open Questions

- None known. The intervals.icu facts the design relies on are in `plan.md`, under "Research".
