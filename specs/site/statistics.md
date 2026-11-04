# Site Specification: The site's own statistics

**Status**: Baseline -- describes the site as it works today
**Verified against**: branch `184-site-statistics` on 2026-11-04
**Code**: `stats/` (`models.py`, `robots.py`, `counting.py`, `middleware.py`, `report.py`, `views.py`,
templates), `stats/static/stats/dashboard.js`, `api/endpoints/stats.py`, the page's ping in
`cycling_site/static/js/cycling_site.js`, the rules `SEE_SITE_STATS` and `COUNTED_AS_TEAM` in
`accounts/roles.py`
**Tests**: `tests/test_stats.py`, `tests/test_role_matrix.py`, `tests/e2e/test_stats.py`,
`test_navbar_fits.py`
**Related**: [site shell](site-shell.md), [accounts](accounts.md), [API](api.md),
[audit log](audit.md)

## Overview

The owners see how the site is used: how many people come, from where, on what, in which language and
what they read; which robots read it and of what kind; what the owners and the admins themselves did;
and what happened on the site -- who joined, events added and approved, registrations, virtual rides.
The site counts this itself, with no third party, and keeps only daily sums.

## User Scenarios

### Story 1 -- An owner reads the statistics (P1)

1. **Given** an owner (or a superuser), **Then** the menu carries "Statistics" after "Virtual ride"
   in the site's frame and in the skins that draw their own (`skins/orange/`, `skins/ubt-dark/`);
   nobody else sees the item, and the page (`/<lang>/stats/`) answers them 403, or the sign-in page
   to a visitor.
2. **Given** the page, **Then** a period is chosen -- today, a week, 30 days (the default), 90 days,
   since the start of the year, a year, all time (from the first day counted) -- and the page names
   its dates. Every period ends today, in the site's own time zone.
3. **Then** it shows, for the period:
   - **People**: visits, page views, pages per visit; a chart of both over time -- by the hour for
     today, by the day up to 92 days, by the week up to two years, by the month beyond -- with the same
     numbers as a table; where visits came from, phones and computers, languages; the 20 most
     viewed pages, named by the title of the event, the article or the news item where the page is one;
   - **Robots**: page views, a chart, the sums by kind, the 20 busiest robots with their kind;
   - **The team** (the admins and the owners): pages opened and changes made (the audit log), a
     chart, and each member's two numbers -- every member of the team listed, idle ones too;
   - **On the site**: members, new and all; members who signed in; Strava connected, new and all;
     registrations for events; events added and approved; events waiting for review now; virtual
     rides finished; and the newest 20 members who signed up, with the date.
4. A chart of one point (today's robots, a first day) is not drawn: its tile says the number.

### Story 2 -- The site counts a page (P1)

1. **Given** a person opens a page, **Then** the page's own script tells the site
   (`POST /api/v1/stats/hit` with the path and the referrer), and the day gets one more view of that
   page, in its hour and its language. A view that came from outside the site -- another site, or
   none -- is also a visit: the other site's host (without `www.`), or "direct", and phone or computer.
2. **Given** a robot -- by its User-Agent, matched against the kinds in `stats/robots.py` --
   **Then** the page it was sent is counted on the server as a robot's view, under "kind:name". A
   User-Agent naming no browser, or naming itself a bot, crawler, spider and the like, is a robot of
   kind "other", named by the word it gives.
3. **Given** an admin or an owner (signed in), **Then** their pages are counted as the team's, per
   member, and never as people's.

### Story 3 -- A program reads the statistics (P2)

1. **Given** an owner's personal token, **Then** `GET /api/v1/stats/?period=` returns what the page
   shows, in the same structure: dates in ISO 8601, a point of a chart as the first day of its
   bucket or "HH:00".

### Edge Cases

- What counts as a page: an HTML answer 200 to a GET, outside the language-free prefixes (the API,
  the admins, media). A request with no User-Agent is not counted at all.
- The ping is dropped, still answering 204, when it does not come from a page of the site
  (`Sec-Fetch-Site` other than same-origin, or an `Origin` of another host), when its sender is a
  robot or a member of the team, and when its path has no language prefix. The page sends none after
  an error answer (where the browser says the status) and, for a page Chrome drew ahead of a click,
  only once it is shown.
- The day is the site's (`TIME_ZONE`), not the reader's, whatever zone a page was drawn in.
- A key from the request -- a path, a referring host, a robot's name -- is cut to 200 characters,
  and a day takes at most 500 new keys of each of these three: past that, a new key is not counted
  under its own name, while the day's totals still count the view.
- Counting never costs the page: a database error while counting is logged and the page served.

## Functional Requirements

- **FR-STA-001**: Only sums per day are stored (`Tally`: day, dimension, key, count) -- never a
  visit, an address, a cookie or a whole User-Agent -- and they are kept for good.
- **FR-STA-002**: People are counted by the page's own script, robots and the team by the server
  (`stats.middleware.CountingMiddleware`, last in `MIDDLEWARE`).
- **FR-STA-003**: Who reads the statistics is `SEE_SITE_STATS` (owner); whose pages are the team's is
  `COUNTED_AS_TEAM` (admin), both in `accounts/roles.py`.
- **FR-STA-004**: The page takes its colours from the skin: lines and bars in the skin's link colour,
  a second line grey and dashed, text in its text colours; Chart.js 4.4.1 is loaded on this page alone.
- **FR-STA-005**: Every robot the calendar treats as one (`BOT_USER_AGENT_MARKERS`) is a robot here
  too (`tests/test_stats.py`).

## Key Entities

- **Tally** (`stats/models.py`): one row per day, dimension and key. Dimensions: `views` and `visits`
  (key: people, bots or team), `hour` ("00".."23", people's views), `page` (path), `source` (host or
  "direct"), `device` (phone or computer), `language`, `bot` ("kind:name"), `team` (a member's id).

## Local assumptions

- None known: the day follows `TIME_ZONE`, the robots are a table of names in `stats/robots.py`.

## API gaps

- None: the page's numbers are `GET /api/v1/stats/`.

## Open Questions

- Visits are views that came from outside the site; with no cookie, one person coming twice is two
  visits, and people are not counted as unique.
- A browser with scripts off is not counted; a robot that runs scripts and calls itself a browser is
  counted as a person.
- The ping is open, as a page's own script needs it to be: a script that sends it again and again
  inflates the numbers. It cannot fill the database (the day's limit of new keys), and nothing stops
  it yet.
