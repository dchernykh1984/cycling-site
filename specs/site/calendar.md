# Site Specification: Finding events (calendar, list, map, feeds)

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `calendar_app/` (views, filters, feeds, `visibility.py`), `calendar_app/templates/calendar_app/`
**Tests**: `calendar_app/tests.py` (calendar, list, map, events API, filters, favorites, default
filters), `tests/test_calendar_toolbar.py`, `tests/test_ics_feed.py`, `tests/test_feeds.py`,
`tests/test_calendar_crawlable.py`, `tests/test_list_site_registration.py`,
`tests/test_pagination_links.py`, `tests/test_locations_payload.py`, `tests/test_location.py`,
`tests/e2e/test_calendar_view.py`, `test_calendar_map.py`, `test_competition_list.py`,
`test_discipline_filter.py`, `test_location_filter.py`, `test_date_filters.py`,
`test_filter_url_length.py`, `test_view_switcher_location.py`, `test_favorite_events.py`,
`test_save_filter_preferences.py`
**Related**: [events](events.md), [locations](locations.md), [accounts](accounts.md) (saved
preferences), [search visibility](search-visibility.md)

## Overview

Three views of the same published events -- a month grid, a list and a map -- share one set of
filters, carried in the address so a filtered view can be bookmarked and shared. Subscriptions
(iCalendar, RSS, Atom) give the same events to calendar apps and readers.

## User Scenarios

### Story 1 -- Browse what is coming (P1)

1. **Given** a visitor opens the calendar, **Then** a month grid shows the published events; a
   multi-day event appears on every day it runs; a "Today" button and a month and year picker move
   the grid (the years reach from the oldest to the furthest visible event, at least this year).
2. **Given** the list view, **Then** it shows upcoming events (not past ones) for the next 30 days,
   a page at a time with numbered pages, a jump-to-page field, and filters kept across pages;
   with a location, direction, discipline or event type chosen, the whole season ahead is shown
   instead; an explicit date range wins over both.
3. **Given** the map view, **Then** events of the next 30 days (or the chosen range) are pinned:
   each location with coordinates gets a marker listing its events with links; several events at
   one place share one marker.
4. **Given** any of the three, **Then** a switcher moves between them keeping the filters; the map,
   which has no location filter of its own, carries the incoming location filter through its links,
   and a chosen date range is remembered for the browser session.
5. **Given** the grid page, **Then** it also links upcoming and running events in plain HTML so
   crawlers can follow them (finished events are not advertised as upcoming).

### Story 2 -- Filter (P1)

1. **Given** the filters, **Then** a reader can choose several event types, directions and
   disciplines, and favorites only, on every view; several countries / regions / cities / venues on
   the grid and the list; a date range on the list and the map. A level whose every option is ticked
   is sent as its parent, and ids travel comma-joined, so a wide selection stays a short address.
2. **Given** several values of one filter, **Then** an event matching any of them is shown, once.
3. **Given** a direction and a discipline both chosen, **Then** they are OR-ed; a location includes
   everything beneath it in the tree.
4. **Given** a junk or unknown id in the address, **Then** it is ignored, not treated as "nothing".
5. **Given** a member with saved preferences opens a calendar page without a query, **Then** they
   are redirected to it with their preferences applied; an explicit query or the reset link is
   left alone (see [accounts](accounts.md)).

### Story 3 -- Follow the season elsewhere (P2)

1. **Given** the iCalendar subscription, **Then** it is a calendar clients accept, carries the same
   filters as the list, links every event back to its page, ends a multi-day event the day after
   its last day, and leaves out hidden and long-finished events.
2. **Given** the "new events" RSS/Atom feed, **Then** the newest approved addition comes first and
   unapproved events never appear; every page declares the news feeds and the calendar declares
   its own.

### Story 4 -- Favorites (P3)

1. **Given** a signed-in member stars an event, **Then** it is saved once per member and event,
   the star reflects it, and "favorites only" filters the grid, list and map; a visitor gets no
   star and the favorites filter is empty for them.

### Edge Cases

- An event's location shown in the list resolves a hidden catch-all venue to its city.
- On the map, a hidden venue is pinned at its city (or region when the city has no point);
  unresolvable or deleted locations are skipped.
- The location tree the filters cascade over is loaded from its own cacheable endpoint, not
  embedded in every calendar page.

## Functional Requirements

- **FR-CAL-001**: Every listing (grid feed, list, map, upcoming rows, search) shows only approved,
  undeleted events the reader may see: hidden events only to admins and up; invite-only events
  only to those let in (`calendar_app/visibility.py`, see [events](events.md)).
- **FR-CAL-002**: The events API behind the grid returns approved events overlapping the requested
  range, including multi-day events that started before it, each with its page address.
- **FR-CAL-003**: Filters: location (multi, includes descendants), event type (multi), direction
  (multi), discipline (multi), date from/to, favorites; comma-joined values are accepted.
- **FR-CAL-004**: The list shows each event's title, dates, types, directions, disciplines,
  country, region, city, venue and links; it links the registration form on the site while it is
  open and not full, before any external registration link; a full or closed form is not linked.
- **FR-CAL-005**: Feeds and subscriptions never carry hidden, unapproved or invite-only events.
- **FR-CAL-006**: Calendar labels (Today, months) are translated in every language.

## Key Entities

- **Competition** (an event): see [events](events.md).
- **Favorite**: one member, one event.
- **EventType**, **DisciplineCategory** (direction) and **Discipline**: the taxonomy the filters use.
  An event carries several event types and several disciplines; its directions are those of its
  disciplines, since every discipline belongs to one direction.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- The map opens over Central Asia (`DEFAULT_CENTER = [48.0, 68.0]`, zoom 5 in
  `calendar_app/templates/calendar_app/map.html`) when there is nothing to fit to.
- "Today", the upcoming window and the 30-day span are reckoned in the site's `TIME_ZONE`
  (`Asia/Almaty`), one zone for every reader.
- The iCalendar subscription names the brand and host in code (`calendar_app/feeds.py`:
  `Universal Bicycle Team`, `@universalbicycle.team`) rather than from the site's settings.

## Open Questions

- None known.
