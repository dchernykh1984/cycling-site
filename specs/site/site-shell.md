# Site Specification: The site around every page

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `cycling_site/` (templates `base.html`, `_setup_hint.html`, `_share_button.html`;
`setup_hints.py`, `context_processors.py`, `middleware.py`, `richtext.py`, `storage.py`), `home/` (home page, site
content, legal pages), `search/`
**Tests**: `home/tests.py`, `tests/test_home_cards.py`, `cycling_site/tests.py`, `tests/test_setup_hints.py`,
`tests/test_share_button.py`, `tests/test_language_switch.py`, `tests/test_locale_cache.py`,
`tests/test_kazakh_account_pages.py`, `tests/test_page_meta.py`, `tests/test_favicon.py`, `search/tests.py`,
`tests/test_template_comments.py`, `tests/test_sign_in_link.py`, `tests/test_signing_out.py`,
`tests/e2e/test_home_page.py`, `test_header.py`, `test_locale.py`, `test_setup_hints.py`,
`test_share_button.py`, `test_reader_timezone.py`, `test_sign_in_returns.py`, `test_sign_out_stays.py`
**Related**: [accounts](accounts.md), [skins](skins.md), [search visibility](search-visibility.md)

## Overview

Every page shares one frame: a sticky navbar (site title, News, Calendar, Map and About when their
pages exist, Ratings ([ratings](ratings.md), right after Calendar), Knowledge Base, Gallery ([gallery](gallery.md)), Virtual ride, Statistics for the owners
([statistics](statistics.md)), Search, the skin chooser, the three language buttons, sign-in or the member's
menu; sign-in brings the reader back to the page it was pressed on, filters and all, except from an
account page, and signing out stays on the page -- or, where a guest may not open it, goes to the
home page in its language), a banner of moderation tasks for moderators, one of requests waiting for a member's answer, one of the events they took part in to rate and, for the owners while none is marked, one asking to mark the agents' account ([ratings](ratings.md))
([accounts](accounts.md)), one setup hint, the page, and a footer with the legal pages and a link to
report a bug. The menu's and the footer's links stay in the page's language: a Wagtail page (the
home page, Map, Knowledge Base) is addressed under its own language's prefix
(`cycling_site/page_mixins.OwnLanguageUrlMixin`), not under the default language's.

**Virtual ride** (`trainer/`, `/<lang>/virtual-ride/`) frames an indoor-trainer page,
`trainer/static/trainer/alatau.html`, in an iframe that may use Web Bluetooth, the screen wake
lock and full screen; a link opens the same page on its own. The page is a static file that loads
its own files from `trainer/static/trainer/alatau/`, in the order it lists them: `alatau.css`, its
words (`text/<lang>.js`), its maps (`maps/`, below), its rider catalogue (`data/`) and its code, a file
per part of it (`js/`: the physics, the ride, the scene, the riders, the devices, the HUD, the site's API and the
rest). The ride is stepped apart from its drawing: the physics (`js/physics.js` -- the speed from
power or gear, the riders' drag, the bots, what a smart trainer is set to) and the ride's state and
step (`js/ride.js` -- the countdown, the rider, the bots, laps, sights, the finish, a plan's steps)
neither read the page nor draw, and nothing else steps the physics. Each frame the ride takes its
step, the trainer is told the grade and the rider's own drag (the rolling resistance of their bike
and CdA x air density from their height, weight and bike, the numbers the ride moves them by), and
the scene and the HUD are drawn from the ride's state; what happened in the step reaches the page
through `rideHooks`. A smart trainer is sent one command at a time, each once it has answered the one
before, as FTMS requires; a trainer that never answers is given two seconds a command and driven all
the same. A trainer that no longer grants control is asked for it once more and, if it still says no,
is shown as not under control and left alone; a grade sent before the trainer reconnected is sent
again. A frame's time is ridden in steps of at most 50 ms, so the ride keeps real time on a device
that draws two frames a second or more; a longer
pause, such as a hidden page, counts as half a second. Production names each file after a hash of
its content, as it names the page, and the page links those names (`cycling_site/storage.py`), so the
page and its files are cached together. The ride
runs in the browser: the page talks to the site only through `Site.req` (`js/site.js`), to
`/api/v1/virtual-ride/` -- who rides, a member's records and rides, the lobby and group races, a
finished ride and its Strava upload. The page is updated from delivered revisions. It speaks the language its address names (`?lang=ru|kk|en`, which the
site's page passes from its own; Russian without one): its texts, units, number and date formats
and the names of its routes, landmarks and riders come from the page itself -- its words in `text/`,
the names in `maps/` and `data/`, the formats from its language and locale (`LANG`, `LOCALE` in `js/page.js`) --
rather than from the translation catalogues: an exception to FR-SHL-006 that keeps the page standing on its own, apart
from the site's templates. A route name the page sends with a saved ride or a group race is in the
language the page spoke then; the page itself shows the routes it knows in its current language,
the profile shows the stored name. A member's page records the ride's track, a point a second: where
the rider is on the route's map (the route's own OpenStreetMap coordinates, simplified, so a turn may
cut a corner), height, distance, speed, power, cadence and pulse. The setup page offers a member who
has not connected Strava to connect it with Strava's button, and tells one who has that the rides go
there, with a link to the profile's Strava card to manage it (`tests/e2e/test_virtual_ride.py`);
the results say when the ride is on Strava ("View on Strava") or why not, with "Send again"; a ride
Strava already has is linked to that activity, never sent twice, and after half a minute of
processing the page says to look in Strava later. A
guest's progress stays in their
browser, as does an unconfirmed account's; for a confirmed member the page saves every finished ride through `/api/v1/virtual-ride/`
(see [the API](api.md)), and their records -- best time per route, peak power, top speed, totals --
are derived from those rides and shown on the profile ([accounts](accounts.md)); rides in demo mode
are kept but never count. Members ride together: the settings page lists who else is on it and the
open group races; a member gathers a race on the chosen route with a start 20 s to 1 h away (the
page offers 30 s to 1 h), others join, and every member's page starts it at the same server time.
"Start" while waiting rides alone and leaves the race to the others: a host who leaves hands it to the
rider who joined next, and only a host alone in it cancels it that way ("Cancel" cancels it for all). Each
race card has "Share": the phone's share sheet, or the link copied, to `/<lang>/virtual-ride/?group=<id>`;
that address opens the trainer with the race marked on its card in words and colour and scrolled
into view, tells a guest to sign in and brings them back to it, and says when the race was cancelled,
has started or does not exist. During a group race, or a free ride
on the same route, each page reports its position about once a second and draws the others
(`trainer/live.py`; rows older than 15 s count as gone). Group results are the members' saved rides,
fastest first; deleting one moves the others up. The settings page is separate from the ride and offers racing, a cadence plan and free riding. It includes rider
height/mass and bicycle type/mass; the rider wears the UBT kit, with third-person view as the
default. Free rides can be finished from the pause menu. During a ride the HUD shows, in one row on top, the speed,
the distance, the metres climbed and the time over a bar of the route (or the plan, or the lap) done; under it the
power, large, with the heart rate (the zone's colour on its heart, the figure white) and the cadence, and the ride's
average power; in a cadence plan, from the countdown on, the step's target beside the power, the cadence coloured by
how far it is from it, the step's average cadence and the list of steps on the left; on the right the grade over the
minimap and, when there are other riders, those nearby with the gaps in seconds; hints read as a large line over
the road. A phone held upright gets one column, a tablet keeps the blocks apart, and nothing animates for a reader
who asked for less motion (issue #434). Record labels keep the date and demo marker distinct. Tests:
`tests/test_virtual_ride.py`, `tests/test_virtual_ride_api.py`, `tests/test_static_storage.py`,
`tests/e2e/test_virtual_ride.py`.

**Maps.** A map is a city, in a folder of its own: `maps/<id>/map.js`, one `addMap({...})` with the
map's data and nothing else (`js/maps.js`) -- its id, the folder's name; its name; its origin, a point
among its routes the scene is laid out from in metres east and south, so a map anywhere keeps its
distances and a rider's track its coordinates; its mountains, when it has a range rising to the south
(how far south of the origin its foot lies at the nearest; a map without them gets none); its routes, each a
key, a name and a description, the points (latitude, longitude, height in metres), whether it is a
loop, the road's width and lanes and the scenery drawn along it (`city` or `gorge`); and the sights
along them, each the object it is built from, a name, a place and the room it takes. Every name is in
ru, kk and en. The page lists each map's file, a line each, in the order the menu shows the cities,
so a new map is its folder and that line; a map without routes is shown as coming soon. A route's key
is its own across every map and stays as it is: the members' saved rides and group races keep it.
The objects the sights are built from are shared by every map, a file each in `objects/`, named after
the object it adds (`addObject('<type>', build)`, `js/landmarks.js`), and listed by the page too; a
new kind of sight is its object's file and that line.
Tests: `tests/test_virtual_ride_maps.py`.

## User Scenarios

### Story 1 -- Read in my language (P1)

1. **Given** a visitor opens the bare address, **Then** they are redirected to the language their
   browser asks for (Russian by default), and that redirect is never cached.
2. **Given** a reader presses a language button (RU, KK, EN), **Then** the same page opens in that
   language -- from a page in any language, whatever the reader chose before, as when a Russian link
   from a chat opens on an English phone -- and the choice holds across pages and when the bare
   address is opened again; a member's
   choice is written to their profile and outranks the cookie. Each button shows the language's code
   as its address writes it -- KK, not the country's KZ -- and names the language in that language,
   for a screen reader and as a pointer's hint (#388).
3. **Given** an address that names its language, **Then** it stays in that language.

### Story 2 -- The home page (P2)

1. **Given** the home page, **Then** it shows the owner's cards in their order, each a heading and a
   rich text per language (a language without its own words falls back as every data field does).
   Every skin draws them as tiles, as many to a row as fit and one to a row on a phone -- the site's
   own skins as cards in their colours, UBT Almaty and Dark UBT in their own style --, the first
   spanning the row when it has no heading or repeats the page's title.
2. **Given** the owner, **Then** they edit the site content -- the navbar title and the tab title per
   language -- in three language tabs, and below it add, change, move up or down and delete cards,
   each in a form of its own with three language tabs; a card with no heading and no text in any
   language is refused. Nobody else sees the edit button; on these pages a guest is sent to sign in
   and any other member gets a 403. The cards are the owner's through the API too
   (`/api/v1/home/cards/`, [API](api.md)).

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
   are not found, nor a place awaiting review but by its proposer and its moderators (FR-LOC-003);
   a bad or out-of-range page number does not fail.

### Edge Cases

- Times are shown in the reader's zone, and the server's "today" is theirs: the page's script keeps
  the browser's zone in a `tz` cookie and `ReaderTimezoneMiddleware` activates it. Until the
  browser has reported one (the first page, a crawler, a feed reader), or when the cookie is not a
  zone, the site's `TIME_ZONE` setting is used (issue #344).
- A missing page answers 404 with the site's template in every language, offering a link home that
  names a language; an address without a language is sent to one first.
- Django request errors and Gunicorn errors (including worker timeouts after application
  initialization, with `--preload` on the host) are mailed to the admins when not in debug.
  Warnings and expected HTTP 503 availability responses are logged without email; an actual
  exception attached to a 503 still notifies admins. This keeps storage retries from flooding
  the mailbox or occupying the web threads with SMTP. SMTP operations have a five-second timeout by default
  (`EMAIL_TIMEOUT`), so reporting an error cannot wait indefinitely. An unavailable server or
  a proxy-generated 502 without an application/server log still needs external monitoring.
  Media is served in production and a missing file is a 404.
- Every page declares a canonical address, a title without stray whitespace, a translated fallback
  description and a social image with its size; an event page's title and description name the
  event, its date and place.

## Functional Requirements

- **FR-SHL-001**: Three languages (ru default, kk, en); the language buttons read RU, KK, EN (#388).
  A string a package ships no Kazakh for -- django-allauth's pages and mails, Django's password
  rules, form errors and CSRF refusal -- would fall back to Russian, the default language; its
  Kazakh is kept in `cycling_site/locale_third_party/`, with the Russian of a Django string its own
  Russian lacks (`tests/test_kazakh_account_pages.py`,
  `registrations/tests.py::FormLabelsInThePageLanguageTests`).
- **FR-SHL-002**: The privacy policy and the terms of use live at stable addresses, are public and
  translated, linked from every footer; the privacy policy states what Strava data is used, what a
  member allowed to manage one's registrations and photos sees and may do ([accounts](accounts.md)),
  how a guest's region is found from the network provider's location and that the location is not
  stored ([calendar](calendar.md)), how the site counts its own visits -- daily sums only, no cookie,
  address or identifier, the team's pages per member ([statistics](statistics.md)) --, that every
  new member agrees with it on the sign-up form or at a provider's first sign-in, and that a member
  who adds people without accounts answers for having their consent, who sees those people's data
  and what deleting them takes away ([accounts](accounts.md), issue #438) -- and links to the
  contact form.
- **FR-SHL-003**: All rich text (home cards, articles, descriptions) goes through one sanitiser:
  scripts and dangerous links dropped, a link to another page opens in a new tab while one to a
  part of the same page (`#...`) stays on it, a limited set of formatting, image size/float and text
  colour kept (`cycling_site/tests.py::SanitizeRichHtmlTests`, `tests/e2e/test_article_contents.py`).
- **FR-SHL-004**: The navbar stays on top with a solid background while scrolling. Its open menu
  wraps whole links and tool groups when needed instead of widening the page, in every locale
  and skin (`tests/e2e/test_interface_rules.py::test_no_tab_scrolls_sideways`).
  A page's heading beside its share button breaks a word too long for the room the button leaves,
  as an event's does, rather than pushing the button off a phone
  (`tests/e2e/test_page_heading_fits.py`). So does an event's description, as an article's body
  does: a chat's name written with commas and no spaces never scrolls a phone sideways
  (`tests/e2e/test_description_fits.py`).
- **FR-SHL-005**: Templates use no multi-line `{# #}` comments (they leak into pages).
- **FR-SHL-006**: Reader-facing names, titles, captions and descriptions are localized data fields
  by default, edited per ru / kk / en in forms and administration. Existing text survives their
  introduction. A document such as a knowledge article may instead belong to one locale and be
  listed only in it. IDs, dates, numbers and URLs are not translated; other exceptions are explicit
  in the area's specification.

## Key Entities

- **SiteContent**: singleton with the navbar title and the home page's tab title per language.
- **HomeCard**: a card of the home page: a heading and a rich text per language, and its position.
- **User.dismissed_hints**: the setup hints a member turned off.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). The default language is Russian (`LANGUAGE_CODE`). The offered languages are a setting, but the
  three of them are also written into the code one by one: the forms, templates and API schemas
  name each `*_ru` / `*_kk` / `*_en` field (`calendar_app/forms.py`, `news/forms.py`,
  `home/forms.py`, `locations/forms.py`, `api/schemas.py` and their templates), and helpers loop over
  a literal `("ru", "kk", "en")` (`api/endpoints/content.py`, `locations/models.py`,
  `cycling_site/skins.py`). A fourth language would need changes in each.
- The virtual ride page carries its own maps (`trainer/static/trainer/alatau/maps/`, a folder per
  city; only Almaty has routes so far) and the UBT kit its rider wears (`data/`). A new map comes with
  a new revision of the page -- its folder and a line in it; the site stores only the route key and
  name the page sends.
- The fallback page description names countries and sports ("cycling, running, cross-country skiing
  -- in Kazakhstan, Kyrgyzstan, Russia and beyond", `base.html`), and the navbar falls back to
  "Cycling" and the footer to "Cycling events" when the site content has no title.

## API gaps

- The navbar title and the tab title (site content) have no API: the owner edits them on the site only.

## Open Questions

- None known.
