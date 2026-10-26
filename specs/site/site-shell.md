# Site Specification: The site around every page

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `cycling_site/` (templates `base.html`, `_setup_hint.html`, `_share_button.html`;
`setup_hints.py`, `context_processors.py`, `middleware.py`, `richtext.py`), `home/` (home page, site
content, legal pages), `search/`
**Tests**: `home/tests.py`, `cycling_site/tests.py`, `tests/test_setup_hints.py`,
`tests/test_share_button.py`, `tests/test_language_switch.py`, `tests/test_locale_cache.py`,
`tests/test_page_meta.py`, `tests/test_favicon.py`, `search/tests.py`,
`tests/test_template_comments.py`, `tests/e2e/test_home_page.py`, `test_header.py`, `test_locale.py`,
`test_setup_hints.py`, `test_share_button.py`, `test_reader_timezone.py`
**Related**: [accounts](accounts.md), [skins](skins.md), [search visibility](search-visibility.md)

## Overview

Every page shares one frame: a sticky navbar (site title, News, Calendar, Map and About when their
pages exist, Knowledge Base, Gallery ([gallery](gallery.md)), Virtual ride, Search, the skin chooser, the three language buttons, sign-in or the member's
menu), a banner of moderation tasks for moderators, one setup hint, the page, and a footer with the
legal pages and a link to report a bug.

**Virtual ride** (`trainer/`, `/<lang>/virtual-ride/`) frames a self-contained indoor-trainer page,
`trainer/static/trainer/alatau.html`, in an iframe that may use Web Bluetooth, the screen wake
lock and full screen; a link opens the same file on its own. The file is kept as delivered and is
not localized (Russian only); its progress stays in the reader's browser. The settings page
is separate from the ride and offers racing, a cadence plan and free riding. It includes rider
height/mass and bicycle type/mass; the rider wears the UBT kit, with third-person view as the
default. Free rides can be finished from the pause menu. Tests: `tests/test_virtual_ride.py`.

## User Scenarios

### Story 1 -- Read in my language (P1)

1. **Given** a visitor opens the bare address, **Then** they are redirected to the language their
   browser asks for (Russian by default), and that redirect is never cached.
2. **Given** a reader presses a language button (RU, KZ, EN), **Then** the same page opens in that
   language and the choice holds across pages and when the bare address is opened again; a member's
   choice is written to their profile and outranks the cookie.
3. **Given** an address that names its language, **Then** it stays in that language.

### Story 2 -- The home page (P2)

1. **Given** the home page, **Then** it shows the site content -- a navbar title and a rich-text body
   per language -- edited by the owner on the site in three language tabs; others get no edit button
   and a 403 on the edit page.

### Story 3 -- Setup hints (P2, issue #319)

1. **Given** a signed-out reader, **Then** every page except the account pages (sign-in, sign-up,
   the "continue with a service" steps) and a missing page asks them to sign in and brings them back
   afterwards; it cannot be closed and is not quoted by search engines.
2. **Given** a member, **Then** one hint at a time names the next thing to set up, in this order: an
   unconfirmed e-mail first (cannot be closed), then calendar preferences (only on the calendar,
   list and map), then the data a race entry needs, then a second way to sign in, then Strava;
   nothing once everything is set; members get none on the account pages (profile, sign-in methods
   and the like) or on the race entry form, which says itself what is missing.
3. **Given** a member turns a hint off (after confirming), **Then** the next one appears; an unknown
   hint is not stored and a foreign return address is not followed.

### Story 4 -- Share a page (P3, issue #327)

1. **Given** a public page -- the calendar, list and map (with their filters), news, a news article,
   search, the legal pages, a public event's participant list -- **Then** a share button beside the
   heading hands the address to the system share sheet, or copies it and says so.
2. **Given** an event page, **Then** a public event shares its address; an invite-only one shares its
   invitation link, and only with the people who may edit it; invitees, hidden events and events
   awaiting review get no button; personal pages have none.

### Story 5 -- Search (P3)

1. **Given** a query, **Then** it finds published pages in the reader's language, approved events,
   news, knowledge articles written in the reader's language, and locations; hidden and deleted ones
   are not found; a bad or out-of-range page number does not fail.

### Edge Cases

- Times are shown in the reader's zone, and the server's "today" is theirs: the page's script keeps
  the browser's zone in a `tz` cookie and `ReaderTimezoneMiddleware` activates it. Until the
  browser has reported one (the first page, a crawler, a feed reader), or when the cookie is not a
  zone, the site's `TIME_ZONE` setting is used (issue #344).
- A missing page answers 404 with the site's template in every language, offering a link home that
  names a language; an address without a language is sent to one first.
- Server errors are mailed to the admins when not in debug; media is served in production and a
  missing file is a 404.
- Every page declares a canonical address, a title without stray whitespace, a translated fallback
  description and a social image with its size; an event page's title and description name the
  event, its date and place.

## Functional Requirements

- **FR-SHL-001**: Three languages (ru default, kk, en); the language buttons read RU, KZ, EN.
- **FR-SHL-002**: The privacy policy and the terms of use live at stable addresses, are public and
  translated, linked from every footer; the privacy policy states what Strava data is used and links
  to the contact form.
- **FR-SHL-003**: All rich text (site content, articles, descriptions) goes through one sanitiser:
  scripts and dangerous links dropped, links open in a new tab, a limited set of formatting, image
  size/float and text colour kept.
- **FR-SHL-004**: The navbar stays on top with a solid background while scrolling. Its open menu
  wraps whole links and tool groups when needed instead of widening the page, in every locale
  and skin (`tests/e2e/test_interface_rules.py::test_no_tab_scrolls_sideways`).
- **FR-SHL-005**: Templates use no multi-line `{# #}` comments (they leak into pages).
- **FR-SHL-006**: Reader-facing names, titles, captions and descriptions are localized data fields
  by default, edited per ru / kk / en in forms and administration. Existing text survives their
  introduction. A document such as a knowledge article may instead belong to one locale and be
  listed only in it. IDs, dates, numbers and URLs are not translated; other exceptions are explicit
  in the area's specification.

## Key Entities

- **SiteContent**: singleton with the navbar title and home body per language.
- **User.dismissed_hints**: the setup hints a member turned off.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). The default language is Russian (`LANGUAGE_CODE`). The offered languages are a setting, but the
  three of them are also written into the code one by one: the forms, templates and API schemas
  name each `*_ru` / `*_kk` / `*_en` field (`calendar_app/forms.py`, `news/forms.py`,
  `home/forms.py`, `locations/forms.py`, `api/schemas.py` and their templates), and helpers loop over
  a literal `("ru", "kk", "en")` (`api/endpoints/content.py`, `locations/models.py`,
  `cycling_site/skins.py`). A fourth language would need changes in each.
- The fallback page description names countries and sports ("cycling, running, cross-country skiing
  -- in Kazakhstan, Kyrgyzstan, Russia and beyond", `base.html`), and the navbar falls back to
  "Cycling" and the footer to "Cycling events" when the site content has no title.

## Open Questions

- None known.
