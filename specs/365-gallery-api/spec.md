# Feature Specification: The gallery through the API

**Feature Branch**: `365-gallery-api`
**Created**: 2026-10-24
**Status**: Implemented (pull request for issue #365)
**Input**: Issue #365 -- everything on the site can be done through the API except the gallery. The
API must do what the gallery's pages do, with the same rights: admins and above may change it, nobody
below. Constitution principle VII asks for the same: what the site does, a program can do too.

## User Scenarios & Testing

### User Story 1 - A program reads the gallery (Priority: P1)

Anybody's program lists the albums and opens an album or a photo, seeing what the pages would show
the same person.

**Acceptance Scenarios**:

1. **Given** no token, a participant's or an organizer's, **Then** `GET /api/v1/gallery/albums/` lists
   the public albums newest first (by the album's date): titles per language, date, cover photo,
   photo count, the linked event's id.
2. **Given** an album, **Then** `GET /api/v1/gallery/albums/{id}` adds its photos in order, each with
   its caption per language, its size as shown, and the addresses of its original and its thumbnail;
   `GET /api/v1/gallery/photos/{id}` returns one photo.
3. **Given** a hidden album, **Then** only an admin or the owner lists or opens it, or a photo in it;
   anybody else gets 404.
4. **Given** an album linked to an event that is no longer public (hidden, deleted, unapproved,
   invite-only), **Then** a reader below admin sees no event id, as the album page shows no event.

### User Story 2 - An admin's program changes the gallery (Priority: P1)

**Acceptance Scenarios**:

1. **Given** an admin or the owner, **Then** they create an album (`POST /albums/`), change it
   (`PATCH /albums/{id}`: titles, date, event, hidden, cover), delete it with its photos and files
   (`DELETE /albums/{id}`), upload photos into it (`POST /albums/{id}/photos/`, multipart `photos`),
   change a photo's caption (`PATCH /photos/{id}`) and delete a photo (`DELETE /photos/{id}`).
2. **Given** an organizer, a participant or a guest token, **Then** every change answers 403; without
   a token, 401.
3. **Given** an album's fields, **Then** they follow the album form: an empty title or date is taken
   from the linked event, a title given by hand wins, only public events may be linked, and an album
   needs a title and a date one way or the other. A refusal is a 422 naming the field.
4. **Given** an upload, **Then** the form's limits hold (files per upload, size of each and of all,
   room left on the disk), each picture is kept byte for byte with a thumbnail made, a file that is
   not a picture is listed in `failed` while the rest are kept, and an album with no cover takes its
   first photo. When no file could be kept the answer is 422.
5. **Given** a cover to pick, **Then** it must be one of the album's photos; `null` lets the first
   photo stand in. Deleting the cover photo makes the next photo the cover.

### Edge Cases

- A PATCH sends only what changes; `title` replaces all three languages, and an unsent title keeps
  its stored translations, an empty one staying empty.
- An album whose event is no longer public cannot be saved with that event kept linked -- the page's
  form refuses the same -- so the PATCH that changes such an album also sends `competition_id: null`
  or another public event.

## Requirements

- **FR-001**: The gallery API reads and writes through the same rules as the pages: the album form,
  the upload form and `gallery/actions.py`, which the pages call too.
- **FR-002**: Rights: reads as the pages (`Album.objects.visible_to`), writes for admins and the owner
  only (`gallery.permissions`).
- **FR-003**: Titles and captions are read and written per language (constitution principle IV); a
  caption is at most 200 characters in each.
