# Implementation Plan: Event and reader time zones

**Branch**: `344-event-timezones` | **Spec**: [spec.md](spec.md)

## Summary

Coordinates to an IANA zone with `tzfpy` (offline polygons, no network); the event's zone is a
cached property over its location's chain; the reader's zone is a cookie set by an inline script and
activated by a middleware.

## Technical Context

- Django `USE_TZ = True`; the database stores UTC. Forms parse a `datetime-local` value in the active
  zone; templates render aware datetimes in the active zone.
- `Location` is a treebeard materialized-path tree: the ancestors of a node are the prefixes of its
  `path`, so the nearest one with coordinates is one query.

## Constitution Check

- **VI (no local hardcoding)**: removes the Almaty assumption from the deadline and from "today";
  `TIME_ZONE` stays a setting, used only for a reader who has not reported a zone.
- **Never invent facts**: a zone comes from the place's own coordinates, never guessed from a name.
- **Approved events**: no stored event is changed; existing deadlines keep their instants.

## Design

1. `locations.models.timezone_of(location)` -> `ZoneInfo`: the location's own coordinates, else the
   nearest ancestor's, else UTC.
2. `Competition.timezone` (a plain property, not cached: the edit view moves an event and then reads
   its zone) calls it; `is_registration_open` uses
   `timezone.localdate(timezone=self.timezone)`.
3. `calendar_app.forms.WallClockDateTimeField` returns the deadline as typed, without a zone (read
   as UTC, so an hour the reader's own zone skips is not refused); `calendar_app.views` gives it the
   event's zone once the location is known (the edit view now applies registration settings after
   setting the location). The edit form's initial value is the deadline as wall-clock in the
   event's zone.
4. `cycling_site.middleware.ReaderTimezoneMiddleware`: activates the `tz` cookie's zone, if valid,
   and keeps it as `request.reader_timezone` (None when not known).
   `base.html`: a one-line script stores `Intl.DateTimeFormat().resolvedOptions().timeZone` in the
   cookie when it differs.
5. `calendar_tags.event_time`: the deadline in the event's zone with its offset, and in the
   reader's when it is known and the offsets differ.

## Cost

`tzfpy` keeps its polygons in memory: about 43 MB more resident memory per process, measured on
macOS; a lookup then takes well under a microsecond.

## Out of scope

Event start times; a zone in the profile; re-dating events already stored.
