# Site Specification: The photo gallery

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-24
**Code**: `gallery/` (models, permissions, images, forms, views, templates, sitemap section in
`cycling_site/sitemaps.py`), `gallery/events.py`, `gallery/translation.py`,
`calendar_app/templates/calendar_app/detail.html` (the event's albums)
**Tests**: `tests/test_gallery.py`, `tests/test_gallery_localization.py`,
`tests/e2e/test_gallery_upload.py`, `tests/e2e/test_gallery_event_picker.py`, `tests/e2e/test_navbar_fits.py`
**Related**: [events](events.md), [site shell](site-shell.md), [search visibility](search-visibility.md);
`gallery/README.md`; issue #349 (the wider gallery idea: bib numbers, external storage)

## Overview

The gallery keeps the club's best moments: a few beautiful photos per race, ride or camp, chosen
and uploaded by the people who run the site. It is a showcase, not a dump of every shot -- so the
photos are kept exactly as they were taken, and only admins and the owner put them there.

## User Scenarios

### Story 1 -- An admin publishes an album (P1)

1. **Given** an admin or the owner, **Then** they create an album -- a title and a date, typed or
   taken from an event they pick -- upload photos into it, pick its cover by clicking a photo (or
   "Make cover" on a photo's page), delete photos, hide the album while it is not ready, and delete
   it. Any admin may change any album, whoever created it.
   Titles have ru / kk / en fields, at least one required without an event. Empty titles take
   the event's actual translation in that language; a typed title wins. An empty date takes the
   event's start date. Picking an event fills the three title fields and the date in the form
   straight away, and they stay editable; a field already changed by hand keeps its text. "No
   linked event" is an explicit choice, and an existing link can be removed without deleting the
   album or changing its titles.
2. **Given** an organizer, a participant or a guest, **Then** they only look: the album form and
   every change answer 403 (or the sign-in page for a guest).
3. **Given** an uploaded photo, **Then** it is kept byte for byte -- every pixel and its metadata --
   once it has proved to be a JPEG, PNG or WebP a browser can show; only a 1000px thumbnail, upright
   and without metadata, is made for the cards.

### Story 2 -- A reader looks at the photos (P1)

1. **Given** `/<lang>/gallery/` -- what "Gallery" in the menu opens -- **Then** it shows every album
   the reader may see by its cover, newest first (by the album's date); an album's page shows its
   photos with the newest other albums as tabs and "View more" back to the gallery; a photo's page
   shows the original, steps through the album with the arrow keys, and offers it to download as it
   was uploaded. `/<lang>/gallery/albums/`, the list's former address, redirects permanently to
   the gallery, keeping its page.
2. **Given** an event with a public album, **Then** the event page lists it under "Photo albums".
3. **Given** a link to an album pasted into a chat, **Then** the chat shows the album's cover.
4. **Given** a linked public event, **Then** the album shows its localized name, start/end dates,
   full visible location, event types, directions and disciplines, omitting missing facts and
   the long description. If the event becomes hidden, deleted, unapproved or invite-only, the
   facts and event link are no longer public.
5. **Given** album titles and photo captions, **Then** pages, tabs, cards, photo pages and share
   metadata use the address's language with the site's usual fallback. Forms and administration
   expose each title; administration exposes each caption. Existing text becomes the RU value,
   and no translation is invented.

### Edge Cases

- A hidden album is seen only by admins and the owner (and whoever created it); readers get 404.
- An album is offered only public events -- not invite-only or hidden ones -- since it takes its
  event's title and is public itself.
- The media disk is shared with event posters, news pictures and protocols: an upload that would
  leave less than `GALLERY_DISK_RESERVE_MB` (200) free is refused, so the gallery never takes the
  last of it. One submission takes at most `GALLERY_MAX_FILES_PER_UPLOAD` (30) files of at most
  `GALLERY_MAX_UPLOAD_MB` (25) each and `GALLERY_MAX_BATCH_MB` (90) together -- Cloudflare in front
  of the site refuses a request over 100 MB with a bare page, so the form says "too much at once"
  and does not send it; a file that is not a picture is reported and the rest kept.
- A JPEG thumbnail is decoded at reduced size, so a 50-megapixel original does not cost hundreds of
  megabytes of memory; a picture of more than 120 megapixels is refused before decoding.

## Functional Requirements

- **FR-GAL-001**: Only admins and the owner (`gallery.permissions.is_admin_plus`) create, change or
  delete albums and photos.
- **FR-GAL-002**: The original is stored and served unchanged; the thumbnail is the only derived file.
- **FR-GAL-003**: Deleting a photo or an album erases it and its files.
- **FR-GAL-004**: Public albums are a sitemap section (`gallery`); the gallery index is in `sections`.
- **FR-GAL-005**: Album titles and photo captions are localized fields, as required by constitution
  principle IV; introducing them preserves existing text.
- **FR-GAL-006**: An album's optional event is selected with a keyboard-accessible searchable
  control. It searches every title language and the event year, ignoring case and matching
  Cyrillic and Latin transliterations (for example, Gran Fondo and its Cyrillic spelling).
  Only public events are offered, only gallery editors may search, and at most 20 choices are
  returned with a request to refine a broader query. The initial form does not load every event.
- **FR-GAL-007**: The event selector and the album show the same localized event facts: name,
  dates, location, types, directions and disciplines; no description. An album may have no event.

## Key Entities

- **Album**: title per locale, date, optional event, cover photo, hidden, created by.
- **Photo**: album, original image (width, height), thumbnail, caption per locale, order, uploaded by.

## Local assumptions

- The gallery's texts call the photos "our races, rides and training camps": the site's own club.

## API gaps

- Reading albums and photos. Publishing them is admins' work, which principle VII leaves out.

## Open Questions

- A photo's files are deleted as its row is (`post_delete` in `gallery/signals.py`), before the
  transaction commits; constitution principle IX asks for after the commit, so a failed delete
  could leave a row without its files.
- The production media disk is about 1 GB. Originals of a few to 25 MB each fill it after a hundred
  or so photos; a larger disk or external storage (issue #349) decides how far the gallery grows.
- Originals keep their metadata, a phone photo's location included; whether to strip location
  before upload is left to the admin uploading.
- The privacy policy does not yet mention photographs of people or how to ask for one to be removed.
