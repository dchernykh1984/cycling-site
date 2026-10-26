# Site Specification: Event photos by bib

**Status**: Baseline -- describes the first slice of issue #349 as built
**Verified against**: branch `349-external-photo-albums` on 2026-10-26
**Code**: `event_photos/` (models, index, dropbox, bindings, actions, permissions, forms, views,
templates, template tags), `api/endpoints/event_photos.py`, `api/endpoints/start_list.py` (bindings on
upload), `cycling_site/urls.py` (`serve_media` refuses the private prefix),
`calendar_app/templates/calendar_app/detail.html`, `accounts/templates/accounts/profile.html`
**Tests**: `tests/test_event_photos.py`, `tests/test_input_length_limits.py`
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
   link to the indexing instructions. Only Dropbox shared folder links are accepted.
2. **When** they add it or press "Refresh participants' tagging", **Then** the index is read and
   checked; on success the photo counts and revision show, otherwise the reason is shown and the last
   published state stays.
3. An index that drops photos without listing them in `removed_photo_ids`, an older revision, or an
   album id already connected elsewhere is refused.

### Story 2 -- A reader finds photos by bib (P1)

1. **Given** an event with albums, **Then** "All photo albums" lists them and a bib search shows the
   photos with that accepted bib (or confirmed by a registration holding it), unless every
   registration holding the bib marked the photo "not me".
2. Each thumbnail opens the photo in Dropbox in a new tab (Dropbox's `preview=` address, or the
   index's own file link).

### Story 3 -- A participant checks their album (P1)

1. **Given** a member registered on the site whose start line carried their registration id, **Then**
   the event page and the profile ("My race photos") link one album per registration.
2. The album shows confirmed photos first, then candidates marked "Check: is this you?".
3. The athlete marks "This is me" or "Not me"; "Not me" removes the photo with a short undo; after
   that the cross is final. A check can become a cross.
4. Without a known bib the album says so and points to the bib search.

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
  is the latest and within `PHOTO_DECISION_UNDO_SECONDS`.
- **FR-EVP-007**: The organizer page shows participants' marks per album and per bib method.
- **FR-EVP-008**: Every page operation has an `/api/v1/event-photos/` counterpart with the same rules.

## Key Entities

- **ExternalAlbum**: event, folder link, localized title and photographer, album id from the index,
  revision, counts, last error, hidden flag.
- **IndexedPhoto** / **BibObservation**: a photo of the index and the bibs on it.
- **IssuedBib** / **IssuedBibEvent**: a bib a start list gave a registration, and its history.
- **PhotoDecision** / **PhotoDecisionEvent**: a registration's mark on a photo, and every change.

## Local assumptions

- Dropbox is the only storage adapter so far (maintainer decision); Google Drive is next.
- The registration's own account counts as the athlete; people entered on the spot without an
  account use bib search only. The representative role of #315 is a stub (`can_represent`).

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
