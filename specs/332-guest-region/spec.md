# Feature Specification: A guest's calendar opens on their region

**Feature Branch**: `332-guest-region`
**Created**: 2026-10-29
**Status**: Implemented (pull request for issue #332)
**Input**: Issue #332 -- a guest saw every country's events at once (of the next 46, 18 in Russia).
The maintainer decided, 2026-10-29:

- a visitor who is not signed in gets the place filter filled with their region; a member gets their
  saved preferences, as before; neighbouring regions are not added;
- the region is the one the site's city nearest to the visitor lies in -- not the region whose
  centre is nearest, since a large region's centre can lie further off than a small neighbour's;
- with no events in that region, the whole calendar is shown;
- a guest who clears the region does not get it back on the next page;
- search engines and messengers' link previews always read the whole calendar;
- the location comes from the network provider (Cloudflare's visitor location headers, turned on
  for the domain by the maintainer the same day), and the privacy policy says so.

## User Scenarios & Testing

### User Story 1 - A guest sees what is near them (Priority: P1)

A rider in Almaty opens a link to the calendar without signing in and sees Almaty's events, not a
month of races in other countries.

**Independent Test**: a request reporting a point next to a city of the site, without a cookie and
from a browser, is redirected to the same page with that city's region in the place filter.

**Acceptance Scenarios**:

1. **Given** a guest whose point lies within `GUEST_REGION_RADIUS_KM` of a city of the site, and
   that city's region has an event still to come, **When** they open the calendar, the list or the
   map without a query, **Then** they are redirected to it with `?location=<region>`.
2. **Given** two regions, **When** the visitor's point is nearer the centre of one but nearer a city
   of the other, **Then** the region of the nearest city is chosen.
3. **Given** no point, a point with no city of the site within the radius, or a region with nothing
   still to come, **Then** the page opens whole, as before.

### User Story 2 - The guest's choice is kept (Priority: P1)

1. **Given** a guest whose region was put in the filter, **When** they clear it, **Then** no page of
   that visit puts it back: a cookie that lasts until the browser closes says it was offered.
2. **Given** an address with any query, **Then** it is shown as asked.

### User Story 3 - Crawlers and previews see the whole calendar (Priority: P1)

1. **Given** a user agent carrying one of `BOT_USER_AGENT_MARKERS` (or none at all), **Then** no
   region is applied: what a search engine indexes and a messenger previews is the whole calendar.

## Requirements

- **FR-001**: The region is found in the request only: the point the network provider adds, the
  site's approved cities and their regions. The point is not stored; the feature keeps nothing but
  the visit cookie.
- **FR-002**: Members are never given a guest's region; their saved preferences apply as before.
- **FR-003**: The radius and the crawler markers are settings, not values in the code.
- **FR-004**: The privacy policy, in the three languages, says how the region is found, that the
  location is not stored, and what the cookie is for.

## Out of Scope

- A "near me" button with the browser's own location, and neighbouring regions (the issue's first
  proposal): the maintainer chose the region alone.
- Folding other places into an "N more elsewhere" line: the filter's chip already names the region
  and clears it in one tap.
- `MAP_HOME_AREAS` stays: a guest from the Almaty region gets the map's Almaty view through it.

## API

Nothing changes in `/api/v1/`: a program asks for the places it wants.
