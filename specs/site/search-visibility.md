# Site Specification: Search visibility

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `cycling_site/urls.py` (`i18n_patterns`), `cycling_site/middleware.py`,
`cycling_site/sitemaps.py`, `cycling_site/indexnow.py`, `cycling_site/summaries.py`,
`cycling_site/jsonld.py`, `cycling_site/context_processors.py` (`search_verification`), `home/seo.py`,
`calendar_app/seo.py`, `calendar_app/listing_seo.py`, `calendar_app/feeds.py`, `base.html`
**Tests**: `tests/test_language_urls.py`, `tests/test_sitemap.py`, `tests/test_structured_data.py`,
`tests/test_listing_seo.py`, `tests/test_landing_pages.py`, `tests/test_indexnow.py`,
`tests/test_page_meta.py`, `tests/test_feeds.py`, `tests/test_ics_feed.py`,
`tests/test_locale_cache.py`, `tests/test_search_setup.py`, `tests/test_listing_index.py`,
`tests/test_account_pages_noindex.py`, `tests/test_localized_links.py`
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
5. **Given** an event page, **Then** `og:description` -- the line a chat shows under a pasted
   link -- is the event's preview text in the page's language, else the sentence about the event
   (date and place) in that language; `meta description`, which search engines read, stays that
   sentence whatever the preview text says (issue #318). The sentence names the event's type
   unless it is the first in the types' order (the usual kind), and a direction's catch-all
   discipline as the direction -- "Road Cycling", not "Other (Road Cycling)" (issue #334).
6. **Given** any page, **Then** `og:title` is the name a view or an editor gave the page for
   sharing, else the name its tab shows -- "Calendar", the home page's own title -- in every skin
   (issue #334).

### Story 2 -- An engine finds the content (P1)

1. **Given** `sitemap.xml`, **Then** it is an index of sections -- Wagtail pages, the calendar's
   month, list and map views and the gallery's index and album list, knowledge, news, events (past
   ones stay, each dated by its last edit or its approval, whichever is later), calendar filter pages, public photo albums -- each entry once per language with its translations; nothing hidden,
   unapproved or invite-only is offered. Its `x-default` is the default language's own address, as
   on the page itself, never the unprefixed address that only redirects.
2. **Given** an event page, **Then** it carries `SportsEvent` data: machine-readable dates (a
   one-day race ends the day it starts), absolute URL, the venue with coordinates and the full address chain,
   the sport from its disciplines, its own preview picture as its image when it has one, and an offer when registration is open here or linked elsewhere
   (registration here wins); markup in a title cannot break out of the block.
3. **Given** a knowledge or news article, **Then** it carries `Article` / `NewsArticle` data with its
   language or date.
4. **Given** the home page, **Then** it carries a `SportsOrganization` and a `WebSite` with a search
   action: the club's name, logo, area and its profiles elsewhere, each from a setting
   (`ORGANIZATION_NAME`, `ORGANIZATION_AREA`, `ORGANIZATION_SAME_AS`, https links only); what is not
   set is not claimed.
5. **Given** any structured data, **Then** it is JSON a search engine can parse as it stands --
   `<`, `>` and `&` as JSON escapes (`cycling_site/jsonld.py`), never HTML character references,
   which a script element does not decode.
6. **Given** `GOOGLE_SITE_VERIFICATION` / `YANDEX_VERIFICATION`, **Then** every page carries the
   ownership tag that console asks for; unset, none is written.
7. **Given** a page with no picture of its own shared in a chat, **Then** it shows the wide
   1200x630 site picture (`static/og-default.png`) as a large card.

### Story 3 -- A filtered calendar is a page of its own (P2)

1. **Given** the list filtered by a city, region or discipline, **Then** its title, heading and
   description name the place or discipline and the number of events, and it reaches the whole
   season ahead; the unfiltered list keeps the site-wide text and the 30-day span.
2. **Given** the calendar, **Then** it links the places and disciplines that hold upcoming events,
   busiest first -- never a catch-all venue or a category's "other" bin, never one whose races are
   over; the same pages reach the sitemap.
3. **Given** a calendar, list or map page, **Then** an engine indexes the page once: the plain page
   and a list about one city, region or discipline name themselves canonical (a list opened on some
   dates names the dateless list, its hreflang alternates follow; a later page of it is itself), and
   every other combination of parameters -- dates on the grid or the map, several filters,
   favourites, `reset` -- and any empty filtered list answer `X-Robots-Tag: noindex`, their links
   still followed (`calendar_app/listing_seo.index_policy`). The plain pages stay indexable even
   when empty: the sitemap lists them.

### Story 4 -- Engines hear about new pages (P2)

1. **Given** an event is approved or a news article published, **Then** its page is submitted to
   IndexNow in all three languages, whatever door it came through; pending and hidden events are not.
2. **Given** no `INDEXNOW_KEY` or no base URL, **Then** nothing is sent; a refusal is logged, never
   raised; the key file at `/<key>.txt` serves the key and any other name is 404.

### Edge Cases

- The account pages (sign-in, sign-up, password reset, profile -- every `account_*` and
  `socialaccount_*` route) answer `X-Robots-Tag: noindex`: the same forms in three languages, with
  nothing a search should lead to.
- A link an author wrote without a language (`/calendar/719/`) is shown with the reader's one
  (`/ru/calendar/719/`) on event, news, knowledge and home pages, as the page is drawn
  (`localized_links`); nothing stored changes, and addresses served without a language (media,
  documents, the API, the sitemap) or already carrying one are left alone.

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
- **Accepted** (maintainer, 2026-10-21: the brand in code does not matter). The default share picture and the home page's logo (`static/og-default.png`, `static/logo-512.png`)
  are the Universal Bicycle Team mark, files rather than settings.

## Open Questions

- None known.
