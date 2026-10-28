# Feature Specification: Virtual ride together, saved to the profile

**Feature Branch**: `392-virtual-ride-multiplayer`
**Created**: 2026-10-28
**Status**: Implemented (pull request #397 for issue #392)
**Input**: Issue #392 -- the virtual ride page saves every finished ride of a member to their account,
shows their records on the profile, and lets members ride together (group races, shared free rides);
guests keep their progress in the browser. The issue's author delivered the implementation as a
patch; the maintainer then asked, in the same pull request, for the page in the reader's language, a
link to a group race, rides sent to Strava as virtual rides, and a voice chat for small rides of about
twenty. This specification was written beside the code, from the code and its tests, at the
maintainer's request to keep Spec Kit's record; it was not reviewed before the code as a new feature
normally is.

## User Scenarios & Testing

### User Story 1 - A member's rides and records live in their profile (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a confirmed member on the page, **When** they finish a race, a cadence plan or a free
   ride, **Then** the ride is saved (`POST /api/v1/virtual-ride/rides`) and their records are derived
   from all their rides: totals, best time per route with attempts, peak power over 5 s, 1, 5 and
   20 min, top speed. A ride in demo mode is kept in the history and never counts.
2. **Given** their profile, **Then** the "Virtual rides" card shows the totals, best times, peaks and
   the last five rides, and links to the page.
3. **Given** a guest, or an account whose address is not confirmed, **Then** the page keeps progress
   in the browser and says how to keep it in a profile.

### User Story 2 - Members ride together (Priority: P1)

1. **Given** the setup page, **Then** a member sees who else is on it and the open group races.
2. **When** a member gathers a group race on the chosen route with a start 30 s to 1 h away, **Then**
   others join, every member's page starts it at the same server time without bots, each page draws
   the others from their reported positions, and places are ranked on the server from the saved times.
3. **Given** a free ride, **Then** riders on the same route see each other.

### User Story 3 - The page speaks the reader's language (Priority: P1)

1. **Given** `/kk/virtual-ride/` or `/en/virtual-ride/`, **Then** every text of the framed page, its
   units, number and date formats and the names of its routes, landmarks and riders are Kazakh or
   English; without a language the page is Russian.

### User Story 4 - A link to a group race (Priority: P2)

1. **Given** a group race card, **When** a rider taps "Share", **Then** the phone's share sheet opens,
   or the link to `/<lang>/virtual-ride/?group=<id>` is copied and the page says so.
2. **Given** that link, **Then** the page opens with the race marked in words and colour and scrolled
   into view; a guest is told to sign in and comes back to it; a cancelled, started or unknown race
   is named as such.

### User Story 5 - Rides go to Strava as virtual rides (Priority: P2)

1. **Given** a member and a site with a Strava application, **Then** the setup page offers "Connect
   with Strava" and the profile card carries the same button; connecting asks Strava for
   `read,activity:write` in a round trip separate from signing in.
2. **Given** a connected member, **When** a ride that is not in demo mode is saved with its track,
   **Then** it is uploaded as a TCX file with `sport_type=VirtualRide`, the results say when it is on
   Strava ("View on Strava") or why not, and "Send again" retries it.
3. **Given** the track, **Then** its positions are the route's own coordinates at the rider's
   distance, a point a second, with height, speed, power, cadence and pulse.
4. **When** the member disconnects Strava, **Then** the grant is revoked at Strava and its tokens
   deleted; nothing ever reads the member's Strava activities.

### User Story 6 - Talking during a group ride (Priority: P3)

1. **Given** a rider of a group race and a site with a media server configured, **Then** they may
   join the race's voice chat in the lobby or during the ride; their microphone starts muted.
2. **Given** a chat, **Then** each rider hears the others of that race only, up to twenty, through
   Cloudflare Realtime's media server; leaving the race leaves its chat.

### Edge Cases

- A ride longer than six hours keeps the first six hours of its track.
- A grant revoked at Strava fails the next upload with its reason and forgets the tokens.
- A rider whose page stops polling drops out of the online list after 15 s, and out of the voice chat
  with it.
- A network that blocks WebRTC's UDP cannot join the voice chat (no TURN relay).

## Requirements

- **FR-001**: Every operation of the page is an API operation under `/api/v1/virtual-ride/` with the
  site's rules, for the session or a personal token; connecting Strava is a browser round trip, like
  signing in.
- **FR-002**: Records are derived from saved rides, never stored; group places are ranked on the
  server, one saving member at a time.
- **FR-003**: Inputs are bounded: ride fields, track points and their count, session descriptions,
  key lists.
- **FR-004**: The media server's session ids and the Strava tokens never reach a page.
- **FR-005**: The privacy policy says what the virtual ride keeps, what other riders see, what goes
  to Strava and how the voice chat travels.

## Key Entities

`VirtualRide`, `GroupRide`, `GroupRideMember`, `LiveRider`, `RideTrack`, `StravaConnection`,
`StravaUpload`, `VoiceSession` (`trainer/models.py`).

## Open Questions

- Route names stored with a ride or a race are in the language the page spoke then; the profile shows
  them as stored. Per-language route names on the server would need the page to send all three.
- The route geometry is the page's own simplified coordinates; a track snapped to the streets would
  need precise street axes (the page can read an OpenStreetMap export, now switched off).
