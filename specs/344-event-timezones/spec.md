# Feature Specification: Event and reader time zones

**Feature Branch**: `344-event-timezones`
**Created**: 2026-10-21
**Status**: Implemented (pull request for issue #344)
**Input**: Issue #344 -- the site reckoned every time in one zone written into its settings
(`Asia/Almaty`), wherever the event and whoever the reader. The maintainer decided:

- an event's zone is worked out on the fly from its place: the location's coordinates, or, when the
  location has none, the nearest place above it that has them; with none anywhere up the chain, UTC;
- a reader's zone comes from their browser;
- when the event's zone and the reader's differ, show both times; when they are the same, show one.

## User Scenarios & Testing

### User Story 1 - Registration closes when the organizer meant (Priority: P1)

An organizer of a race in Tokyo types "registration until 20:00" on the 14th. Registration closes
at 20:00 Tokyo time, whoever typed it and from wherever.

**Why this priority**: a deadline read in the wrong zone shuts riders out early or lets them in late.

**Independent Test**: an event at a venue with Tokyo coordinates, deadline entered as 20:00; at
19:59 Tokyo time it is open, at 20:00 it is closed.

**Acceptance Scenarios**:

1. **Given** an organizer creating or editing an event, **When** they enter a deadline, **Then** the
   wall-clock time they typed is read in the event's zone, whatever zone their own browser is in, and
   the form says so.
2. **Given** an event with a stored deadline, **When** its organizer opens the edit form, **Then** the
   deadline shows in the event's zone, as it was typed.
3. **Given** an event without a deadline, **Then** registration stays open until the end of the
   event's last day in the event's zone.

### User Story 2 - The reader sees times in their own zone (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a reader whose browser is in a zone, **Then** the times the site shows (comments,
   submissions, protocol versions, moderation records) are in that zone, and "today" -- the upcoming
   list, the calendar's windows -- is their today.
2. **Given** an event page with a registration deadline, **When** the event's zone and the reader's
   have the same offset at that moment, **Then** the deadline is shown once with its UTC offset;
   **when** they differ, **Then** it is shown in the event's zone and again in the reader's, each
   with its offset.
3. **Given** a reader whose browser has not reported a zone yet (the very first page, a crawler),
   **Then** the site's default zone (`TIME_ZONE`) is used and the deadline is shown once, in the
   event's zone.

### Edge Cases

- A location with no coordinates takes the zone of the nearest place above it that has them
  (venue -> city -> region -> country); with none, UTC.
- A point at sea answers with a fixed-offset zone (`Etc/GMT+2`); that zone is used as it is.
- A zone the browser sends that is not a known IANA name (or is malformed) is ignored, and the
  default zone is used.
- An event whose location changes is reckoned in the new place's zone: a stored deadline keeps its
  instant, so the edit form then shows it in the new zone's wall-clock.

## Requirements

### Functional Requirements

- **FR-001**: The event's zone is computed on every use from coordinates; nothing about it is stored.
- **FR-002**: The deadline entered by an organizer is the event zone's wall-clock time.
- **FR-003**: Registration open/closed decisions use the event's zone.
- **FR-004**: The reader's zone comes from a `tz` cookie the page's own script sets from the browser;
  the server activates it per request when it is a valid IANA zone.
- **FR-005**: An event-bound time is shown with its offset, plus the reader's time when the offsets
  differ.

### Key Entities

- **Location** (existing): `lat`, `lng`, its ancestors.
- **Competition.timezone** (computed): the event's zone.

## Success Criteria

- **SC-001**: No time zone of a place is written into code; the site's `TIME_ZONE` is only the
  fallback for a reader whose browser has not reported one.
- **SC-002**: Unit tests pin the zone lookup, the fallbacks, the deadline in Tokyo and the cookie;
  a browser test pins the cookie being set and a comment time shown in the reader's zone.

## Assumptions

- Events carry dates only, no start times; start times are out of scope (issue #344).
- A zone setting in the member's profile is out of scope: the browser's zone is used.
- Deadlines stored before this change keep their instants. They were typed in `TIME_ZONE`
  (`Asia/Almaty`), so an event elsewhere shows the same instant in its own zone's wall-clock.
