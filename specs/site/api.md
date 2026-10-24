# Site Specification: The API

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `api/` (`router.py`, `auth.py`, `schemas.py`), `api/endpoints/`; django-ninja, served at
`/api/v1/`
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
   is created approved -- unless its geography is still pending. The event's author or an admin may
   update it, resubmit it after rejection and soft-delete it; only an admin may hide or unhide it;
   descriptions are sanitised and size-limited. An event's link preview text is read and written
   per language like its title (up to 200 characters each; a PATCH carrying one language clears
   the others). Reads preserve empty languages, so writing a response back keeps the chat's
   date-and-place fallback in those languages (issue #318).
3. **Given** locations, **Then** the tree can be read; an organizer may get or create a city's
   catch-all venue; a venue is created approved by an organizer and proposed by a participant;
   regions and cities are always proposed (organizer and up), countries created by admins only;
   updating and deleting is admin and up.
4. **Given** news, **Then** admins create, update and soft-delete articles; **given** the knowledge
   base, members manage their own drafts and admins publish articles (a news item carries every
   language, a knowledge article its one).
5. **Given** disciplines and event types, **Then** they can be listed with their names per language.

### Story 2 -- The timing tools exchange race data (P1)

1. **Given** the event's upload token (`competition_token`), **Then** a tool fetches the participants
   (only entries that count, category ids included, relay member names), uploads and fetches start
   lists, group-start times, finish times and remote control-point times per device, and uploads
   protocols -- an HTML file, a structured document (`protocols/schema/protocol-document-v1.json`),
   or both from one run ([protocols](protocols.md)).
2. **Given** a device uploads its stream, **Then** it carries the `client_revision` it is at: an
   older revision, or a different snapshot at the same revision, is refused with 409; an identical
   re-send or a newer revision replaces the stored one, and the stored revision is echoed back so a
   device that lost its state can resume.
3. **Given** the finish-protocol generator posts a live-stats snapshot (each bib mapped to an opaque
   set of named values), **Then** the site stores it as it is, without interpreting the keys, and
   anyone may read one bib's values for an approved, visible event -- which is how a watch data
   field (Garmin Connect IQ) shows a rider their place and gaps.

### Edge Cases

- No token where one is needed: 422; an unknown or malformed token: 401; an event not approved: 401.
- Every request string and list is bounded, and the error names the limit instead of failing on
  the server: an over-long content field (a link, a name, a description) is a 422; a device stream
  over its limits (items, item length, device id, body kept under 2 MB) is a 400.
- The event listing gives admins everything; anyone else gets approved events that are neither
  hidden nor invite-only, plus their own submissions; deleted events only on request, to an admin
  (all) or a signed-in author (their own).

## Functional Requirements

- **FR-API-001**: Routers: `/competitions/`, `/news/`, `/knowledge/`, `/locations/`, `/disciplines/`,
  `/event-types/`, `/participants/`, `/protocols/`, `/start-list/`, `/group-times/`,
  `/finish-times/`, `/remote-points/`, `/live-stats/`.
- **FR-API-002**: Personal tokens belong to participants and up (generated on the profile); the
  upload token belongs to an event and is managed by its managers and its author (see
  [events](events.md)).
- **FR-API-003**: Writes keep the same rules as the site: roles, moderation, sanitising, soft delete,
  audit (the audit log records the token's member).
- **FR-API-004**: What a participant or an organizer reads or changes on the site is also available
  here (constitution principle VII); each area's specification lists what is still missing under
  "API gaps", and what is left out on purpose as an **Exception** with its reason.

## Key Entities

- **Start list / timing uploads** (`GroupTimesUpload`, `FinishTimesUpload`, `RemotePointUpload`):
  one stream per event, device (and control point), with a client revision.
- **Live stats snapshot**: per event, per competitor.

## Local assumptions

- **Accepted** (maintainer, 2026-10-21: the brand in code does not matter). The API's title describes it as a "cycling portal" (`api/router.py`), though it serves every sport.
- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). The request and response schemas name each language's field (`api/schemas.py`), and the content
  endpoints accept the literal locales `("ru", "kk", "en")` (`api/endpoints/content.py`).

## Open Questions

- None known.
