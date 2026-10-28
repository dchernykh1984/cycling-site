# Site Specification: Event photos by bib

Originals may be JPEG, PNG, WebP, HEIC/HEIF, TIFF, BMP, GIF or AVIF. Formats outside
JPEG/PNG/WebP must include a separate web-compatible preview in the index. The site
uses that preview for thumbnails and keeps the original storage link for downloads;
it never decodes camera formats or rewrites originals.

**Status**: Baseline -- describes the first slice of issue #349 as built
**Verified against**: branch fix/event-photo-gallery on 2026-10-27; a member's manager (issue #315) against
branch `315-managing-registrations` on 2026-10-28
**Code**: `event_photos/` (models, index, dropbox, bindings, actions, permissions, forms, views,
templates, template tags), `api/endpoints/event_photos.py`, `api/endpoints/start_list.py` (bindings on
upload), `cycling_site/urls.py` (`serve_media` refuses the private prefix),
`calendar_app/templates/calendar_app/detail.html`, `accounts/templates/accounts/profile.html`
**Tests**: `tests/test_event_photos.py`, `tests/e2e/test_event_photos.py`, `tests/test_input_length_limits.py`
**Related**: [gallery](gallery.md), [registrations](registrations.md), [protocols](protocols.md), [api](api.md);
feature design in `specs/349-external-photo-albums/`

## Overview

A photographer's Dropbox folder, shared "anyone with the link", holds the race photos and a
`photo-index.v1.json` saying which bibs are on which photo. The event's creator or an admin connects
the folder; the site reads the index with its own Dropbox app (no organizer token) and keeps a copy.
Readers find photos by bib; a member opens "Photos with me" -- one album per registration, from the
bib StartProtocolMaker gave that registration -- and marks each photo "this is me" or "not me".
Thumbnails come from Dropbox and are kept by the site; a click opens the photo in Dropbox.

## User Scenarios

### Story 1 -- An organizer connects an album (P1)

1. **Given** the event's creator or an admin, **Then** "Manage event photos" on the event page opens a
   form: folder link, title (prefilled from the event) and photographer in three languages, with a
   link to the indexing instructions (the Sport Photo Indexer program, or the skill in the Sport Photo
   Indexer project). Only Dropbox shared folder links are accepted.
2. **When** they add it or press "Refresh participants' tagging", **Then** the index is read and
   checked; on success the photo counts and revision show, otherwise the reason is shown and the last
   published state stays.
3. An index that drops photos without listing them in `removed_photo_ids`, an older revision, or an
   album id already connected elsewhere is refused.

### Story 2 -- A reader finds photos by bib (P1)

1. **Given** an event with albums, **Then** its single "Photos from the event" link opens an overview
   with personal registration cards, photo sources and bib search. The search shows the
   photos with that accepted bib (or confirmed by a registration holding it), unless every
   registration holding the bib marked the photo "not me".
2. Each thumbnail opens the photo in Dropbox in a new tab (Dropbox's `preview=` address, or the
   index's own file link).
3. **Given** a signed-in reader and a search with results, **Then** "Download all (ZIP, size)" gives
   the found photos' originals as one archive; a guest is offered sign-in that returns to the search.

### Story 3 -- A participant checks their album (P1)

1. **Given** a member registered on the site whose start line carried their registration id, **Then**
   the event photo overview and the profile ("My race photos") link one album per registration.
2. The album shows confirmed photos first, then candidates marked "Check: is this you?".
3. The athlete marks "This is me" or "Not me"; "Not me" removes the photo with a short undo; after
   that the cross is final. A check can become a cross.
4. Without a known bib the album says so and points to the bib search.
5. "Download all (ZIP, size)" gives the album's originals as one archive; a photo marked "not me" is
   not in it.
6. **Given** a member who manages another member's registrations and photos ([accounts](accounts.md),
   issue #315), **Then** the member's registrations appear among theirs in "My race photos", on the
   event's overview and in `GET /event-photos/me/registrations`, each card titled with the member's
   name and bib; they open the member's albums ("Photos of ...") and mark the photos as the member
   would (`can_represent`). The member sees and marks only their own; once the link ends, the former
   manager gets a 404, as any stranger does.

## Functional Requirements

- **FR-EVP-001**: Reading uses only the site's Dropbox app credentials (`DROPBOX_APP_KEY`,
  `DROPBOX_APP_SECRET`); folder links are cleaned to `rlkey`/`st`.
- **FR-EVP-002**: The index is checked by `event_photos/index.py` (schema, paths, SHA-256 digests,
  bib text, manual marks bound to the original's digest, limits from settings) before any write.
- **FR-EVP-003**: Import compares the revision again under the album's row lock and writes in bulk;
  a removed photo keeps its row and marks and returns with them.
- **FR-EVP-004**: Thumbnails are stored under `MEDIA_ROOT/private/event_photos/`, which `serve_media`
  refuses, and served by a view applying the album's visibility with `Cache-Control: private`;
  a changed digest makes a new one and the old file is deleted after commit.
- **FR-EVP-005**: A start-list upload recomputes `IssuedBib` from field 10 of every device's lines
  (`event_photos/bindings.py`): absent versus empty field, stage bibs within `START_LIST_MAX_STAGES`,
  conflicts suspend the bib, history in `IssuedBibEvent`. The upload's response is unchanged.
- **FR-EVP-006**: Decisions are per registration and photo; undo reverts one recorded change while it
  is the latest and within `PHOTO_DECISION_UNDO_SECONDS`. Repeating "Not me" is idempotent on the
  page and API, even after the photo leaves the personal grid; it preserves the original undo
  window and never exposes hidden photos.
- **FR-EVP-007**: The organizer page shows participants' marks per album and per bib method.
- **FR-EVP-008**: Every page operation has an `/api/v1/event-photos/` counterpart with the same rules.
- **FR-EVP-009**: Photo pages have a breadcrumb from Events to the actual event, its photo
  overview, then the current source album, participant name or searched bib. The event title
  always opens the event, never a different photo level.
- **FR-EVP-010**: Thumbnails preserve the entire frame, including portraits and on hover. Their
  captions sit below the image. Image alternatives do not duplicate adjacent link captions;
  unavailable previews show a translated fallback while the original link remains usable.
- **FR-EVP-011**: The browser requests at most two nearby previews concurrently. A temporary 503
  or a dropped request is retried with a growing, randomly spread delay (never sooner than
  Retry-After, at most 30 s apart, 12 times) once the card is in view again, so a busy server
  delays a preview instead of losing it. Each web process allows at most two concurrent storage
  thumbnail downloads and uses four Gunicorn threads so marks need not wait for them. Cached
  thumbnails bypass this limit, and a disk below its reserve refuses before downloading. Busy or
  temporarily unavailable thumbnails return private, non-cacheable 503 with Retry-After on both
  site and API. Index imports retain their own timeout.
- **FR-EVP-012**: A separate opt-in integration check uses real Dropbox app authentication to read
  a secret-configured fixture index and decode one thumbnail, without writing storage or the
  site's database. CI runs it on trusted pull requests and main; fork code receives no credentials,
  and Dependabot's pull requests, which get no Actions secrets, skip it.
- **FR-EVP-013**: "Download all" streams a ZIP of the originals as they are read from storage, writing
  nothing to disk: a registration's album (its owner and the event's managers) or a bib's search
  results (signed-in readers only, since every byte passes through the site; the link is `nofollow`).
  One archive at a time per web process; another answers "try again in a minute" on the page and
  503 with Retry-After over the API. An archive over `PHOTO_ARCHIVE_MAX_BYTES` (by the index's
  sizes) is not offered and answers 413 over the API. An original over
  `PHOTO_ARCHIVE_MAX_FILE_BYTES`, or one storage cannot give after one short retry, is left out and
  listed with its link in a text file inside the archive. Equal file names get a number.

## Key Entities

- **ExternalAlbum**: event, folder link, localized title and photographer, album id from the index,
  revision, counts, last error, hidden flag.
- **IndexedPhoto** / **BibObservation**: a photo of the index and the bibs on it.
- **IssuedBib** / **IssuedBibEvent**: a bib a start list gave a registration, and its history.
- **PhotoDecision** / **PhotoDecisionEvent**: a registration's mark on a photo, and every change.

## Local assumptions

- Dropbox is the only storage adapter so far (maintainer decision); Google Drive is next.
- The registration's own account counts as the athlete; people entered on the spot without an
  account use bib search only.

## API gaps

None: the pages' operations are all in `/api/v1/event-photos/`.

## Binding review

Restored bindings remain usable but carry a visible `review` state in personal cards and galleries.
The organizer sees the registration, bib, source device and revision that need checking in the
start-list diagnostics, including foreign registration IDs and stage limits.


## Automatic producer and review corrections

SportPhotoIndexer offers one local automatic button: bib OCR first, then whole-person appearance
matching, selected by default; OCR only is also available. The one-album boundary, model downloads,
provisional thresholds and unmeasured pilot accuracy are documented in the feature recognition
contract. Appearance observations are always candidates. The site validates normalized regions
and active manual-review locks before publication; vectors never enter its database or the index.

Manager album listings include hidden photos and their flag through the API, just as on the page.
Personal covers use confirmed photos with usable thumbnails; candidates use a placeholder. Own
confirmations remain visible even without a current bib binding. Personal API cards include counts,
confirmed count, state, participant/category and a token-protected thumbnail URL. Photo marks,
undo and manager moderation keep the current gallery page. Start-list references work for past
events too; dates do not invalidate registration IDs or historical bibs.

## Open Questions

Pilot precision/recall, CPU time and useful appearance thresholds still need measurements on real
photos. Cross-album appearance matching and additional storage connectors remain future slices.
