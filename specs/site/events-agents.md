# Site Specification: The events import agents

**Status**: Baseline -- describes the system as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `agent/` (shared pipeline), `instagram_agent/`, `telegram_agent/`, their guidance files and
source lists (`events_sources.yaml`, `instagram_accounts.yaml`, `telegram_channels.yaml`), workflows
`agent.yml`, `instagram-agent.yml`, `telegram-agent.yml`
**Tests**: `agent/tests/`, `instagram_agent/tests/`, `telegram_agent/tests/`,
`tests/test_agent_schedules.py`
**Related**: [API](api.md), [events](events.md), [locations](locations.md); the `events-agents` skill
holds the operating detail

## Overview

Three scheduled jobs read announcements -- web calendars and organizer sites, Instagram club
accounts, Telegram channels and groups -- ask a language model to extract concrete upcoming events,
and propose them to the site through the API as a service account. Everything they propose waits
for a human to approve it.

## User Scenarios

### Story 1 -- New events arrive for review (P1)

1. **Given** a nightly run, **Then** each source is read in order, events with a real date in the
   text are extracted with titles, descriptions and places in every site language, placed on the
   location tree, checked against everything the site knows, and proposed as pending.
2. **Given** a date shown only in an image, **Then** the event is left out rather than guessed; links
   are taken only from the page's real links, and coordinates only when the text gives them or a
   geocoder finds them.
3. **Given** the maintainer reads a run, **Then** its summary names every proposed event with link
   and place, every skipped candidate with its reason, and per-source counts.

### Story 2 -- Each event links to itself (P2)

1. **Given** an announcement found on a listing, **Then** the event's link opens that event, never
   the listing, the forum index or the channel feed; for Telegram the post's own address is built in
   code (public or private channel, forum topic included).

### Story 3 -- No duplicates (P2)

1. **Given** a candidate matching an existing event -- by name across scripts (Cyrillic folded to
   Latin), date and place -- or a soft-deleted one, **Then** it is not proposed again.
2. **Given** a venue already on the tree under another spelling, **Then** it is reused rather than
   added again.

### Edge Cases

- A run stops once it has proposed its quota; sources are read in a fixed order so small local
  sources are not starved by large aggregators.
- Instagram needs Graph API credentials that expire about every 60 days; without them the agent
  proposes nothing and says why.
- Scheduled runs drift (GitHub cron is best-effort) or are skipped during Actions incidents.

## Functional Requirements

- **FR-AGT-001**: Agents propose only through the API and only as pending; they never approve, edit
  an approved event, or delete.
- **FR-AGT-002**: A run is started by the schedule or on the maintainer's request only; every run
  costs money at the language-model provider.
- **FR-AGT-003**: The model never supplies a URL or a date of its own: links come from the page,
  dates from the text, Telegram addresses from code.
- **FR-AGT-004**: Each source may carry a free-text hint for the model; the maintainer's guidance
  files steer what matters and in what order.

## Key Entities

- **Source** (web, Telegram, Instagram): kind, address, optional hint.
- **Candidate event**: titles, descriptions and places per language, dates, links, type and
  disciplines chosen from the site's ids, coordinates when known.

## Local assumptions

- The extraction prompt ranks sports in code: "cycling first, and also running, triathlon and
  cross-country skiing" (`agent/llm.py`), and asks for exactly ru / kk / en with Russian as the
  fallback text; the site's language list and sport list are not read from settings or data.
- The source order is tuned in code for Kazakh sources first (`agent/sources.py`); the geography
  ladder itself lives in the guidance file, which is data.
- The package describes itself as discovering "cycling events" (`agent/__init__.py`).

## Open Questions

- None known.
