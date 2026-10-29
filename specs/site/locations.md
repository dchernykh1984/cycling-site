# Site Specification: Geography (locations and the map)

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `locations/` (models, views, `maps.py`), the location cascade in
`calendar_app/templates/calendar_app/_location_cascade.html` and `_location_filter.html`
**Tests**: `locations/tests.py`, `locations/test_maps.py`, `calendar_app/tests.py` (location proposals
in the event form, map resolution), `tests/e2e/test_location_cascade.py`, `test_locations_map.py`,
`test_location_proposal.py`, `test_location_filter.py`
**Related**: [events](events.md), [calendar](calendar.md); the `locations` skill holds the rules for
keeping the tree clean by hand

## Overview

Every event sits on a four-level tree: country, region, city (any settlement), venue -- the actual
start point. Members propose new places; admins approve geography. A public map page shows the
places, and lets managers maintain the tree.

## User Scenarios

### Story 1 -- Place an event (P1)

1. **Given** the event form, **Then** a cascade of country, region and city selects (each filled
   after the one above) offers the city's real venues and a mini-map of existing venues; picking a
   marker selects that venue.
2. **Given** a city without the right venue, **Then** the member may propose a new one with a point
   on the mini-map and its name in each language -- Russian required, a language left empty stays
   empty and reads as the Russian one; a participant's proposal waits for approval, an organizer's
   is approved -- unless the city above it is itself still pending.
3. **Given** the start point is unknown, **Then** the event is attached to the city's hidden
   catch-all venue ("Other location", named in every language). The map pins it at its city and it
   offers no map links, even if a point was given to it; keeping it without one is a rule of
   curation (the `locations` skill), not something the code enforces.

### Story 2 -- Approve geography (P1)

1. **Given** an admin, **Then** pending locations are listed for moderation and may be approved or
   rejected; approving also approves pending ancestors; approving a city approves its catch-all.
2. **Given** an organizer approves an event on a pending branch, **Then** the geography stays
   pending and the approval is refused until an admin approves the branch.
3. **Given** a proposed city is rejected, **Then** its branch is dropped and its events are moved to
   the "other location" -- refused when a published event or registrations or an approved location
   still depend on it.

### Story 3 -- Maintain the tree (P2)

1. **Given** a participant, **Then** they may propose a venue only, which waits for approval; an
   organizer's venue is approved at once (unless its city is pending), while a region or city they
   create is a proposal; an admin creates any node, approved directly, and only admins create
   countries.
2. **Given** an admin, **Then** they may edit names (per language), move a node (a level change only
   when it has no children and no events; never under its own descendant), hide it (twice restores),
   and soft-delete it -- refused while active descendants or events depend on it; the catch-all can be
   neither moved, unhidden nor deleted.
3. **Given** the map page, **Then** a visitor sees markers for places with points -- gathered into
   numbered clusters where they crowd, as on the calendar's map ([calendar](calendar.md)); a participant
   and up also gets an "add a location" button; an admin also sees a paginated, filterable hierarchy
   table with edit/hide/delete actions that keep the filter, and an edit link in marker popups. The
   filter is the calendar's place filter: a venue is typed into its own field straight away, without
   its country, region and city picked first ([calendar](calendar.md), Story 2).

### Edge Cases

- A hidden node is never a marker; a hidden venue resolves to its city's point, or the region's.
- New nodes sort after the real ones and before the catch-all; ties fall back to creation order.
- Concurrent tree mutations are serialised so a node is never orphaned or nested too deep.
- Map links (the services the deployment offers, with local brand names) appear only for a venue
  with its own point -- never for a city, region, country, catch-all or hidden venue.

## Functional Requirements

- **FR-LOC-001**: Exactly four levels; an event attaches at a venue (depth 4); nothing nests under a
  venue.
- **FR-LOC-002**: Approving or rejecting geography is admin and up only; event moderation (organizer
  and up) never approves geography on its own.
- **FR-LOC-003**: Pending locations are visible only to their proposer and to admins.
- **FR-LOC-004**: Deletion is soft; redirects after an action follow only a same-origin `next`.
- **FR-LOC-005**: All embedded maps use the shared `_map_layers.html` component, which disables
  Leaflet's flag-bearing attribution prefix. Map and satellite layers keep their provider credits
  visible, including when the reader switches layers.

## Key Entities

- **Location**: tree node with names per language, coordinates (optional), hidden / deleted flags,
  sort order; the catch-all mapping (**LocationFallback**) per city.
- **LocationProposal**: a pending node, its proposer and status.

## Configuration

- `MAP_SERVICES`: the catalogue of map services an event's start point can be opened in -- for each,
  its label (translated where it is shown), its URL with `{lat}`, `{lng}` and `{zoom}` filled in, and
  for a service that captions its pin, the parameter that carries the place's name. Another service
  is another entry; the catalogue knows 2GIS, Yandex, Google, Apple and OpenStreetMap.
- `MAP_LINK_SERVICES` (environment, comma-separated): which of them an event page offers, in this
  order. By default the services that work everywhere -- Google, Apple, OpenStreetMap. The
  deployment currently lists 2GIS and Yandex first, then Google, Apple and OpenStreetMap
  (`cycling_site/settings/prod.py`). A name the catalogue does not describe is skipped and reported
  at startup (`locations.W001`); a catalogue entry that cannot be filled in -- no label, or a URL
  naming anything but `{lat}`, `{lng}` and `{zoom}` -- is an error that stops `migrate`, and with it
  the deploy (`locations.E001`).

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- The location cascade's mini-map, the locations map page and the location form's coordinate
  picker open over Central Asia (`[48.0, 68.0]`, zoom 5) when there is nothing to fit to.
- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). The catch-all venue is named by looping over a literal `("ru", "kk", "en")`
  (`locations/models.py`), and the location form names each language's field.

## Open Questions

- None known.
