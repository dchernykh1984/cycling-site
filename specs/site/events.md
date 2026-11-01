# Site Specification: An event's life (submit, review, edit, report, invite)

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `calendar_app/` (models, forms, views, `visibility.py`, `preview_image.py`, `tracks.py`),
`calendar_app/static/calendar_app/route_track.js`,
`registrations/views.py` (`can_manage`), `cycling_site/context_processors.py`
(moderation banner)
**Tests**: `calendar_app/tests.py` (model, submit, moderation, detail, edit, comments, reports,
materials, upload token, rich description, several event types), `calendar_app/test_timezones.py`,
`tests/test_invite_only_events.py`,
`tests/test_clone_competition.py`, `tests/test_preview_image.py`, `tests/test_preview_text_form.py`,
`tests/test_competition_link_order.py`, `tests/test_event_form_fields.py`,
`tests/test_event_wording.py`, `tests/test_moderation_banner.py`, `tests/test_event_ics.py`,
`tests/test_top_events.py`, `tests/test_moderation_history.py`, `tests/test_concurrent_review.py`,
`calendar_app/test_tracks.py`, `tests/test_route_track_page.py`,
`assistant/tests/test_chat.py`,
`tests/e2e/test_competition_form.py`, `test_add_to_calendar.py`,
`test_competition_materials.py`, `test_description_editor.py`, `test_resubmit.py`,
`test_pending_moderation.py`, `test_invite_only_events.py`, `test_competition_link_order.py`,
`test_map_links_menu.py`, `test_route_track.py`
**Related**: [calendar](calendar.md), [registrations](registrations.md), [protocols](protocols.md),
[locations](locations.md), [events agents](events-agents.md), [gallery](gallery.md)

## Overview

Anyone confirmed can propose an event; organizers publish directly and moderate everyone else's.
An event's page gathers what a rider needs -- dates, the place with a map and map links,
registration, documents, results and materials, then the description and the discussion. The site
calls every entry an "event" whatever its kind -- in Russian "meropriyatie", never "sorevnovanie".

## User Scenarios

### Story 1 -- Propose an event (P1)

1. **Given** a participant submits the form, **Then** the event is created **pending approval**;
   an organizer's submission is published at once -- unless it stands on a city or region still
   awaiting approval, when it waits too.
2. **Given** the form, **Then** it takes a title (required in Russian, optional in Kazakh and
   English), a rich-text description (sanitised, size-limited, edited with a bundled Quill editor),
   a start date and an optional end date (not before the start), several event types and several
   disciplines (both optional), a location from the tree or a new venue
   proposed in a city (see [locations](locations.md)), a registration link, links and files for
   announcement, regulations, route and results (files: PDF, Office documents, GPX, KML, ZIP or
   images, up to 10 MB; the route takes KMZ, TCX, FIT and GeoJSON too), and for link previews an
   image and a line of text per language (up to 200 characters; a chat shows about the first 80 and
   cuts the rest, the form says so).
3. **Given** an invalid field -- a missing title or date, a link longer than its column, an end
   before the start, an over-long category name -- **Then** the form comes back with a translated
   field error, never a server error, and keeps what was entered.
4. **Given** an organizer, **Then** they may also enable registration on the site, choose its mode
   and options (see [registrations](registrations.md)), and make the event invite-only;
   participants are not offered these.
5. **Given** someone who may edit an event, **Then** "copy" opens the form filled from it --
   registration settings, categories and the link preview text included, dates and last year's
   results not.

### Story 2 -- Review (P1)

1. **Given** an organizer or above, **Then** the moderation page lists pending events (and, for
   admins, pending locations and reported events); approving or rejecting is also
   possible from the event's own page; a rejection needs a reason.
2. **Given** an event is rejected, **Then** its author sees the reason and its history and may edit
   and resubmit it, returning it to pending; history accumulates across rounds.
3. **Given** an event's venue was proposed with it under an approved city, **Then** approving the
   event approves the venue too. **Given** the geography above the venue is itself still pending,
   **Then** only admins see the event in the queue, an organizer cannot approve it, and an admin's
   approval approves the branch with it (see [locations](locations.md)).
4. **Given** a pending event, **Then** its page is visible only to its author and to moderators;
   moderators -- an organizer author included -- get approve and reject on it; it has no star,
   comments or registration.
5. **Given** there is something to moderate, **Then** a banner under the menu tells each moderator
   how many items wait for them and where, counting only what they may act on.
6. **Given** an admin opens an event, **Then** the foot of its page lists its way through review,
   oldest first -- added, rejected with the reason, resubmitted, approved, returned for review --
   each with its time and who did it (#741). An old event lists what was recorded then: its
   creation, its rejections and its last approval.
7. **Given** two moderators act on one pending event at once, **Then** the first decision stands
   and the second is refused, as on an event already reviewed.

### Story 3 -- Keep it current (P2)

1. **Given** the author or a manager, **Then** they may edit the event (fields prefilled, the
   registration deadline as the wall-clock at the event's place, issue #344), delete it, and manage its
   materials (named links in order; rows half filled are refused without losing the rest of the
   edit; script URLs refused).
2. **Given** a manager, **Then** they may hide an event (taken down: visible to admins in listings
   and to its managers on its page) and show it again, and delete its comments.
3. **Given** a manager or the event's author, **Then** they see its upload token and may regenerate
   or delete it; the timing apps use it to send results (see [API](api.md)).
4. **Given** someone who may edit or moderate an event, **Then** its page shows how a link to it
   looks in a chat: the title and the preview text in the page's language, or the date and the
   place when that language has none (issue #318). Nobody else sees the block; the line itself
   lives only in a meta tag (see [search visibility](search-visibility.md)).

### Story 4 -- Report and discuss (P3)

1. **Given** a participant reads a published event, **Then** they may comment (line breaks kept; no
   author e-mail exposed) and report it as inaccurate (reason optional); a second open report by
   the same member is ignored, reporting again after a dismissal is allowed, and the event stays
   public; pending and hidden events cannot be reported.
2. **Given** an admin, **Then** reported events appear once in the queue with their reports, and
   dismissing clears them; organizers do not see reports.

### Story 5 -- Invite-only events (P3, issue #313)

1. **Given** an organizer marks an event invite-only, **Then** a key is issued and only the people
   who may edit it, those who opened its invitation link while signed in, and its registered
   riders see it -- in lists, the grid, the map, search and on its page.
2. **Given** the invitation link, **Then** a visitor not signed in -- a person, or a messenger
   previewing the pasted link -- sees the event's name, preview line and picture, unindexed, with a
   sign-in that comes back to the link (issue #351); signing in lets the reader in and drops the key
   from the address. An event awaiting review or taken down asks to sign in with no preview; a wrong
   key says nothing; a new link shuts the old one but keeps those already in.
3. **Given** an invite-only event, **Then** the sitemap, feeds, iCalendar, public API and landing
   pages never carry it, and its page asks not to be indexed; while it waits for review only
   admins review it. One exception: a rider's live stats stay readable by anybody, as a watch reads
   them (`GET /live-stats/{id}/{bib}`). An invite-only event keeps out whoever is not invited; it is
   not a secret one, and a race can be watched from the roadside (maintainer, 2026-10-31).

### Story 6 -- Put an event into one's own calendar (P3, issue #398)

1. **Given** a published event's page, **Then** "Add to calendar" beside "Share", drawn like it
   (the icon alone on a phone, a tap reaching 44px), leads to the event's own calendar file
   (`/<lang>/calendar/<id>/event.ics`, see [calendar](calendar.md)): one whole-day entry in the
   page's language that the reader's calendar offers to add once. An event awaiting review or
   rejected has no button.

### Story 7 -- Top events (P3)

1. **Given** an admin or the owner on an event's form, **Then** a "Top event" box with a line on
   what it does marks the event; anybody else is not offered it, a forged one is ignored, and the
   author editing a top event leaves the mark as it was. A clone starts without it.
2. **Given** a top event, **Then** it goes first wherever events are listed: at the head of the
   list above a divider, first in its day on the calendar, first at its place on the map, first
   among the nearest events (see [calendar](calendar.md)).

### Story 8 -- Add or edit an event by talking (P2, issue #353)

1. **Given** an organizer or anyone above on the event's add page, or on the edit page of an event
   they manage, **Then** the event assistant's chat fills the form from what they tell it, and the
   form's own button saves it (see [event assistant](assistant.md)).

### Story 9 -- The route on the event's map (P2)

1. **Given** an event whose route file holds a track -- GPX, KML, KMZ, TCX, FIT, GeoJSON, or a ZIP
   of them, told by its bytes rather than its name --, **Then** the event's map draws every track in
   it (a GPX file without tracks: its routes) as a line in the skin's route colour, with the start
   marker above it and arrows along it, about 90 px apart on screen, for the way it runs. A line
   under the map says what the arrows show. The map opens on the whole track and the start; a city's
   point standing in for a venue without one is no start, so the map then opens on the track
   alone. Without a track the map opens on the start as before.
2. **Given** a route link and a route file, **Then** the page offers both, each when it is there:
   "Link to the track" opens the link in a new tab, "Download the track" saves the file. A route
   file that holds no track -- a PDF of the route, say -- keeps its "Route" button, which opens it.
3. **Given** a reader of the event, **Then** `GET /api/v1/competitions/{id}/track` gives the same
   line as a GeoJSON feature with the file's address (see [API](api.md)).

### Edge Cases

- An event is soft-deleted; a deleted comment is erased.
- An event's time zone is worked out from its place on every use (`Competition.timezone`,
  `locations.models.timezone_of`): the venue's coordinates, else the nearest place above it that has
  them, else UTC. Nothing about it is stored, so moving an event moves its zone.
- Registration closes at its deadline or, without one, at the end of the event's last day; the
  overall and per-category limits close it too (see [registrations](registrations.md)).
- A preview image is normalised: an enormous one is scaled down keeping its shape, a tiny one or a
  non-image refused, camera metadata stripped, transparency kept as PNG, photos stored as JPEG.
- The event page lists registration, documents, protocols and materials before the description;
  uploaded documents follow the same order and a URL takes precedence over a file -- but for the
  route, whose link and file are both offered (Story 9).
- A route file is read once, on the first visit after it arrives, and its line kept beside the event
  (`CompetitionTrack`, keyed by the file's name), so the next visit reads no file. The line is
  thinned to within 5 m, and further until at most 4,000 points remain; a file over 10 MB, one that
  declares XML entities, or one that breaks its reader draws nothing, and a file missing from the
  disk is tried again on the next visit.
- Map links on the event page -- the services the deployment offers, in its order (see
  [locations](locations.md), Configuration) -- appear only for a venue with its own point, in one
  menu behind a "Link to the start point" button, however many there are (#335); each answers a tap
  across 44 px and opens in a new tab.
- On a phone an event's title shares its row with the page's buttons (share, add to calendar,
  favourite); a word too long for the room they leave breaks, rather than pushing the page sideways.

## Functional Requirements

- **FR-EVT-001**: Statuses: pending approval, approved, rejected; approving twice or approving a
  rejected event is refused; resubmitting works only from rejected.
- **FR-EVT-002**: Who may: submit -- participant and up; publish directly, moderate, enable
  registration, make invite-only, use the event assistant on the events they manage -- organizer
  and up. A *manager* of an event is an admin or above, or its author while an organizer. Hide and
  unhide, delete comments, see the invitation link and replace it -- managers;
  edit (materials included), delete, resubmit, see and manage the upload token -- managers and the
  author whatever their role; dismiss reports, mark a top event -- admins and up.
- **FR-EVT-003**: Deleting is soft (`is_deleted`); a deleted event is seen by nobody.
- **FR-EVT-004**: Who sees a published event: everybody, unless it is hidden (managers on its page,
  admins in listings) or invite-only (managers, invitees, registered riders whose entry is not
  rejected).
- **FR-EVT-005**: Rich descriptions are sanitised on save and in the admin; translations do not leak
  across locales on save.
- **FR-EVT-006**: Redirects after moderation follow only a safe `next`, never downgrading https.
- **FR-EVT-007**: Every save that moves an event to another status adds a step to its history --
  the new and the previous status, who (the signed-in user or the API token's owner; the author for
  the event being added; the reviewer for an approval or a rejection) and when, and a rejection's
  reason -- whatever door it took: the moderation page, the author's resubmission, the status field
  of the Wagtail admin, the API. An approval or a rejection also records its reviewer and time on
  the event, unless the save already named them; a save that keeps the status records nothing. The
  steps of the events added before the history was kept come from the audit log's creation entry,
  the rejection history and the last approval; their resubmissions are unknown. Only admins and
  owners see it: at the foot of the event's page, and as `moderation_history` in the API's event
  detail, with `approved_by_id` and `approved_at` when the event is approved; null for everyone
  else.

## Key Entities

- **Competition** (event): titles and descriptions per locale, dates, status and rejection history,
  author, location, event types, disciplines, document links/files, preview image and preview text
  per locale, registration
  settings, upload token, hidden / deleted / invite-only / top flags and invite key.
- **CompetitionInvite**: a member let in by the invitation link.
- **CompetitionComment**, **CompetitionReport** (open or dismissed), **CompetitionMaterial**
  (ordered named link).
- **CompetitionTrack**: the line the route file draws, kept with the name of the file it was read
  from; empty for a file that holds no track.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). Russian is the base language of an event: its Russian title is required, the Kazakh and English
  ones optional (`calendar_app/forms.py`).
- **Accepted** (maintainer, 2026-10-21: the brand in code does not matter). An event page's meta description ends with the brand written in code ("Details, start point and
  results on the Universal Bicycle Team calendar.", `calendar_app/models.py`).

## API gaps

- Approving and rejecting an event: organizers and up moderate on the site; the API only resubmits
  a rejected one.
- Registration on the site and invite-only events: enabling registration, its mode, options and
  categories; making an event invite-only and issuing a new invitation link.
- Materials (named links), uploaded documents (announcement, regulations, route, results) and the
  link-preview image: the API takes the five links only.
- The upload token: the API shows it to the event's author and admins, but cannot regenerate or
  delete it.
- Commenting on an event, reporting it as inaccurate, and accepting an invitation.

## Open Questions

- None known.
