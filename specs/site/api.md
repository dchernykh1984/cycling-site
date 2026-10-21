# Site Specification: The API

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `api/` (`router.py`, `auth.py`, `schemas.py`, `endpoints/`), django-ninja under `/api/v1/`
**Tests**: `api/tests.py`, `registrations/tests.py` (participants), `protocols/tests.py`,
`tests/test_input_length_limits.py`, `tests/e2e/test_api_to_front.py`
**Related**: [events](events.md), [locations](locations.md), [news and knowledge](news-and-knowledge.md),
[protocols](protocols.md), [registrations](registrations.md), [events agents](events-agents.md)

## Overview

One API, two kinds of client. Members' tools -- the events agents first among them -- read and
write content with the member's personal token. The timing tools used at a race -- the start-list
maker, the chronometer, the finish-protocol generator -- exchange start lists, timings, live stats
and protocols with the event's upload token. The API has no language prefix.

## User Scenarios

### Story 1 -- A member's tool manages content (P1)

1. **Given** a `Authorization: Bearer <api token>` header, **Then** the request acts as that active
   member; reads also work without a token, as a visitor.
2. **Given** an organizer creates an event through the API, **Then** it waits for review; an admin's
   is created approved -- unless its geography is still pending. The event's author may update,
   resubmit after rejection and soft-delete it; descriptions are sanitised and size-limited.
3. **Given** locations, **Then** the tree can be read; an organizer may get or create a city's
   catch-all venue; a venue is created approved by an organizer, proposed by a participant;
   updating and deleting is admin and up.
4. **Given** news, **Then** admins create, update and soft-delete articles; **given** the knowledge
   base, members manage their own drafts and admins publish articles; texts per language.
5. **Given** disciplines and event types, **Then** they can be listed with their names per language.

### Story 2 -- The timing tools exchange race data (P1)

1. **Given** the event's upload token (`competition_token`), **Then** a tool fetches the participants
   (only entries that count, category ids included, relay member names), uploads and fetches start
   lists, group-start times, finish times and remote control-point times per device, and uploads
   protocols.
2. **Given** two devices write the same stream, **Then** a compare-and-set on `client_revision`
   keeps one from overwriting the other unseen.
3. **Given** a live-stats snapshot, **Then** it is stored per event, and one competitor's live stats
   are read by event and bib.

### Edge Cases

- No token where one is needed: 422; an unknown or malformed token: 401; an event not approved: 401.
- Every request string and list is bounded (items, item length, device id, body size kept under 2
  MB); an over-long value is a 422 with the limit named, not a server error.
- Hidden, deleted and invite-only events are not served to the public listing, whoever asks.

## Functional Requirements

- **FR-API-001**: Routers: `/competitions/`, `/news/`, `/knowledge/`, `/locations/`, `/disciplines/`,
  `/event-types/`, `/participants/`, `/protocols/`, `/start-list/`, `/group-times/`,
  `/finish-times/`, `/remote-points/`, `/live-stats/`.
- **FR-API-002**: Personal tokens belong to participants and up (generated on the profile); the
  upload token belongs to an event and is managed by its managers (see [events](events.md)).
- **FR-API-003**: Writes keep the same rules as the site: roles, moderation, sanitising, soft delete,
  audit (the audit log records the token's member).

## Key Entities

- **Start list / timing uploads** (`GroupTimesUpload`, `FinishTimesUpload`, `RemotePointUpload`):
  one stream per event, device (and control point), with a client revision.
- **Live stats snapshot**: per event, per competitor.

## Local assumptions

- The API's title describes it as a "cycling portal" (`api/router.py`), though it serves every sport.

## Open Questions

- None known.
