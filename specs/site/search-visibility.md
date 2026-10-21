# Site Specification: Search visibility

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `cycling_site/urls.py` (`i18n_patterns`), `cycling_site/middleware.py`,
`cycling_site/sitemaps.py`, `cycling_site/indexnow.py`, `cycling_site/summaries.py`,
`calendar_app/seo.py`, `calendar_app/listing_seo.py`, `calendar_app/feeds.py`, `base.html`
**Tests**: `tests/test_language_urls.py`, `tests/test_sitemap.py`, `tests/test_structured_data.py`,
`tests/test_listing_seo.py`, `tests/test_landing_pages.py`, `tests/test_indexnow.py`,
`tests/test_page_meta.py`, `tests/test_feeds.py`, `tests/test_ics_feed.py`,
`tests/test_locale_cache.py`
**Related**: [calendar](calendar.md), [site shell](site-shell.md); the `search-visibility` skill holds
the operational detail (issue #275)

## Overview

Search engines see one address per page per language, a sitemap of everything public, structured
data on events and articles, filtered calendar pages that are pages about a city or a discipline,
and an IndexNow notice whenever something is published.

## User Scenarios

### Story 1 -- An engine indexes every language (P1)

1. **Given** a reader-facing page, **Then** it answers at `/ru/`, `/kk/` and `/en/`; the prefix
   decides the language over the cookie, `Accept-Language` and the profile.
2. **Given** a bare address, **Then** it is redirected (302, keeping the query string) to the
   reader's language, and the redirect is not cached; a signed-in reader lands on their chosen
   language.
3. **Given** a machine-facing address (`/api/v1/`, admins, media, documents, `/i18n/`, sitemap,
   robots, the IndexNow key), **Then** it carries no prefix, and a missing API address is a 404,
   not a redirect.
4. **Given** any page, **Then** it declares itself canonical, `hreflang` alternates for all three
   languages plus `x-default` (all absolute), Open Graph and Twitter tags, and the feeds.

### Story 2 -- An engine finds the content (P1)

1. **Given** `sitemap.xml`, **Then** it is an index of sections -- Wagtail pages, knowledge, news,
   events (past ones stay), calendar filter pages -- each entry once per language with its
   translations; nothing hidden, unapproved or invite-only is offered.
2. **Given** an event page, **Then** it carries `SportsEvent` data: machine-readable dates (no end
   date for a one-day race), absolute URL, the venue with coordinates and the full address chain,
   the sport from its disciplines, and an offer when registration is open here or linked elsewhere
   (registration here wins); markup in a title cannot break out of the block.
3. **Given** a knowledge or news article, **Then** it carries `Article` / `NewsArticle` data with its
   language or date.

### Story 3 -- A filtered calendar is a page of its own (P2)

1. **Given** the list filtered by a city, region or discipline, **Then** its title, heading and
   description name the place or discipline and the number of events, and it reaches the whole
   season ahead; the unfiltered list keeps the site-wide text and the 30-day span.
2. **Given** the calendar, **Then** it links the places and disciplines that hold upcoming events,
   busiest first -- never a catch-all venue or a category's "other" bin, never one whose races are
   over; the same pages reach the sitemap.

### Story 4 -- Engines hear about new pages (P2)

1. **Given** an event is approved or a news article published, **Then** its page is submitted to
   IndexNow in all three languages, whatever door it came through; pending and hidden events are not.
2. **Given** no `INDEXNOW_KEY` or no base URL, **Then** nothing is sent; a refusal is logged, never
   raised; the key file at `/<key>.txt` serves the key and any other name is 404.

## Functional Requirements

- **FR-SEO-001**: Every navigation link points straight at a prefixed address (no redirect needed).
- **FR-SEO-002**: Every catalogue entry is translated and none is fuzzy; link-preview strings reach
  the reader translated.
- **FR-SEO-003**: Feeds: news RSS/Atom, new events RSS/Atom by approval date, iCalendar with the list
  filters (see [calendar](calendar.md)).

## Key Entities

- None of its own; it reads events, articles, locations and disciplines.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: the brand in code does not matter). Filtered-list descriptions name the brand in code ("... on the Universal Bicycle Team calendar",
  `calendar_app/listing_seo.py`).
- IndexNow is chosen because Yandex honours it; that choice suits any audience and assumes nothing.

## Open Questions

- None known.
