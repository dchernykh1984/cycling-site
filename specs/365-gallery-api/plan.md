# Implementation Plan: The gallery through the API

**Branch**: `365-gallery-api` | **Spec**: [spec.md](spec.md)

## Summary

A django-ninja router at `/api/v1/gallery/` (`api/endpoints/gallery.py`) over the existing models.
Nothing new is stored. The rules the pages follow are reused, not rewritten: `AlbumForm` validates an
album's fields, `PhotoUploadForm` the upload limits, and storing uploads, the fallback cover and
deleting move out of the views into `gallery/actions.py`, which both doors call.

## Constitution Check

- **IV (languages)**: titles and captions per ru / kk / en, an empty translation never filled from
  another on write.
- **VII (API by default)**: closes the gallery's API gap; admin-only work, which VII leaves optional,
  is included because the issue asks for it.
- **VIII (one fact, one home)**: one album form, one upload form, one module of actions for both doors.
- **IX (nothing lost)**: deletes go through the same code as the pages (files with their rows).
- **X (input checked, data private)**: bounded titles and captions, uploads proved to be pictures, a
  hidden album and a non-public event's id never shown below admin.
- **XI (the API keeps its promises)**: new endpoints only; nothing existing changes.

## Design

1. `gallery/actions.py`: `save_uploads`, `keep_a_cover`, `delete_photo`, `delete_album`; the views
   call the first, second and last.
2. Reads: `GET /albums/`, `GET /albums/{id}` (with photos), `GET /photos/{id}`, optional token.
3. Writes: `POST /albums/`, `PATCH /albums/{id}`, `DELETE /albums/{id}`, `POST /albums/{id}/photos/`,
   `PATCH /photos/{id}`, `DELETE /photos/{id}`, token required, admin and above.
