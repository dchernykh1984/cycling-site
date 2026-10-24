# Site Specification: Finding events (calendar, list, map, feeds)

**Status**: Baseline -- describes the site as it works today
**Verified against**: PR #343 on 2026-10-24
**Code**: `calendar_app/` (views, filters, feeds, `visibility.py`), `calendar_app/templates/calendar_app/`
**Tests**: `calendar_app/tests.py` (calendar, list, map, events API, filters, favorites, default
filters), `tests/test_calendar_toolbar.py`, `tests/test_ics_feed.py`, `tests/test_feeds.py`,
`tests/test_calendar_crawlable.py`, `tests/test_list_site_registration.py`,
`tests/test_pagination_links.py`, `tests/test_locations_payload.py`, `tests/test_location.py`,
`tests/e2e/test_calendar_view.py`, `test_calendar_map.py`, `test_competition_list.py`,
`test_discipline_filter.py`, `test_location_filter.py`, `test_date_filters.py`,
`test_filter_url_length.py`, `test_view_switcher_location.py`, `test_favorite_events.py`,
`test_save_filter_preferences.py`, `test_calendar_phone_list.py`, `test_period_nav.py`,
`test_calendar_busy_day.py`, `test_filter_chips.py`, `test_filter_toggle.py`
**Related**: [events](events.md), [locations](locations.md), [accounts](accounts.md) (saved
preferences), [search visibility](search-visibility.md)

## Overview

Three views of the same published events -- a month grid, a list and a map -- share one set of
filters, carried in the address so a filtered view can be bookmarked and shared. Subscriptions
(iCalendar, RSS, Atom) give the same events to calendar apps and readers.

## User Scenarios

### Story 1 -- Browse what is coming (P1)

1. **Given** a fresh visitor opens the calendar, **Then** a phone lists the remaining days of the
   month and a wide screen opens the month grid; Month explicitly opens the grid. A chosen layout
   survives the visit without switching on resize. A multi-day event appears once in a list and
   on every day in the grid; three events and +N keep a busy grid day compact.
2. **Given** the list view, **Then** it shows upcoming events (not past ones) until the current month's end,
   a page at a time with numbered pages, a jump-to-page field, and filters kept across pages;
   with a location, direction, discipline or event type chosen, the whole season ahead is shown
   instead; an explicit date range or floating-month marker wins over both.
3. **Given** the map view, **Then** events until the current month's end (or the chosen range) are pinned:
   each location with coordinates gets a marker listing its events with links; several events at
   one place share one marker.
4. **Given** any of the three, **Then** a switcher moves between them keeping the filters; the map,
   which has no location filter of its own, carries the incoming location filter through its links,
   and a chosen date range is remembered for the browser session. Explicit dates or a floating
   current-month link win over saved dates; a bare calendar visit restores the session period.
5. **Given** the grid page, **Then** it also links upcoming and running events in plain HTML so
   crawlers can follow them (finished events are not advertised as upcoming).

### Story 2 -- Filter (P1)

1. **Given** a phone, **Then** filters start folded behind a named icon showing their count;
   active filters have removable chips and the panel retains its open state during the visit.
   **Given** the filters, **Then** a reader can choose several event types, directions and
   disciplines on every view, and a signed-in member also "favorites only"; several countries / regions / cities / venues on
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

- **FR-CAL-001**: Every listing shows only approved, undeleted events the reader may see, and
  invite-only events only to those let in (`calendar_app/visibility.py`, see [events](events.md)).
  Hidden events appear to admins and up in the grid, the list and the map, but never in the
  upcoming rows under the grid or in search, whoever asks.
- **FR-CAL-002**: The events API behind the grid returns approved events overlapping the requested
  range, including multi-day events that started before it, each with its page address.
- **FR-CAL-003**: Filters: location (multi, includes descendants), event type (multi), direction
  (multi), discipline (multi), date from/to, favorites; comma-joined values are accepted.
- **FR-CAL-004**: The list shows each event's title, dates, types, directions, disciplines,
  country, region, city, venue and links; it links the registration form on the site while it is
  open and not full, before any external registration link; a full or closed form is not linked.
- **FR-CAL-005**: Feeds and subscriptions never carry hidden, unapproved or invite-only events.
- **FR-CAL-006**: Calendar labels are translated in every language; Kazakh period labels put
  the year before the month or days. Shared period controls offer days, weekend, week, month and
  a year picker, step by the selected kind and return keyboard focus when a picker closes.
- **FR-CAL-007**: Phone List rows show city and sport, and preserve the remaining FR-CAL-004
  facts and Info link in expandable row details. Desktop retains the table.
- **FR-CAL-008**: The approved PR #343 styling uses filled active tabs and contrasting period
  frames in light/dark (maintainer approval, 2026-10-24); all skins retain named 44px tap targets.

## Key Entities

- **Competition** (an event): see [events](events.md).
- **Favorite**: one member, one event.
- **EventType**, **DisciplineCategory** (direction) and **Discipline**: the taxonomy the filters use.
  An event carries several event types and several disciplines; its directions are those of its
  disciplines, since every discipline belongs to one direction.

## Configuration

- `MAP_HOME_AREAS` maps named areas to their south-west and north-east corners. The deployment currently names
  `almaty`, bounded by `[43.05, 76.55]` and `[43.90, 77.45]`. If every mapped selected place lies
  in one area, the map opens on it; otherwise it fits matching event markers.
- `MAP_DEFAULT_VIEW` sets the center and zoom when neither an area nor markers are available.
  The deployment's current default is `[48.0, 68.0]`, zoom 5; changing it needs configuration,
  not a template change.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: the brand in code does not matter). The iCalendar subscription names the brand and host in code (`calendar_app/feeds.py`:
  `Universal Bicycle Team`, `@universalbicycle.team`) rather than from the site's settings.

## API gaps

- Favorites: starring an event and reading one's starred events.

## Open Questions

- None known.
