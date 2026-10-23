# Gallery

Photo albums at `/<lang>/gallery/`, linked from the navbar.

- **Album**: title per ru / kk / en (typed, or taken from that language of the linked event), date,
  optional event (`competition`),
  cover photo, hidden flag. Only admins and the owner create and change albums -- any admin any
  album; everybody else, organizers included, only looks (`gallery/permissions.py`). The gallery
  is the club's showcase of its best shots, curated, not a place for every photo of a race.
- **Event choice**: search by name in any title language or by year; Cyrillic and Latin
  transliterations match. The results show dates, location, types, directions and disciplines;
  the same facts appear on the album while its event is public. "No linked event" creates a
  standalone album with its own title and date; removing a link keeps those values.
- **Translations**: album titles and photo captions use django-modeltranslation. The album form
  and Django administration edit titles per language; photo captions are edited in administration.
  Existing text is preserved as RU; a missing translation uses the site's usual fallback.
- **Cover** ("main picture"): picked in the album form (click a photo) or with "Make cover" on a
  photo page. Until one is picked, the first photo stands in (`Album.cover_photo`). The cover is
  the album's card in "All albums" and the image a chat shows for the album link.
- **Photos** are kept as they were uploaded, byte for byte (`gallery/images.py`): JPEG, PNG or WebP,
  checked to be a picture first. The photo page and "Download" serve that original; only a 1000px
  thumbnail, upright and without metadata, is made for the cards. Files go under
  `MEDIA_ROOT/gallery/<album>/`; deleting a photo deletes its files.
- **Limits**: `GALLERY_MAX_FILES_PER_UPLOAD` (30) and `GALLERY_MAX_UPLOAD_MB` (25), from the
  environment, and `GALLERY_MAX_BATCH_MB` (90) for one submission as a whole: Cloudflare refuses a
  request over 100 MB, so the form stops a bigger batch before sending it. A file that is not an
  image is reported and the rest of the batch is kept. An upload
  that would leave less than `GALLERY_DISK_RESERVE_MB` (200) free on the media disk -- shared with
  event posters, news pictures and protocols -- is refused.
- **Pages**: `gallery_index` (newest album, others as tabs), `gallery_album`, `gallery_albums`
  (all albums by cover), `gallery_photo` (one photo, arrow keys step through the album).
- **Event page**: `calendar_app/detail.html` lists the event's public albums.
- **Search**: public albums are the `gallery` sitemap section; the index and the album list are in
  `sections`.

Tests: `tests/test_gallery.py`, `tests/test_gallery_localization.py`,
`tests/e2e/test_gallery_event_picker.py`. Specification: `specs/site/gallery.md`.
