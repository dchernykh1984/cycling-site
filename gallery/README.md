# Gallery

Photo albums at `/<lang>/gallery/`, linked from the navbar.

- **Album**: title (typed, or taken from the linked event), date, optional event (`competition`),
  cover photo, hidden flag. Organizers and up create albums; an organizer manages their own, an
  admin manages every album (`gallery/permissions.py`).
- **Cover** ("main picture"): picked in the album form (click a photo) or with "Make cover" on a
  photo page. Until one is picked, the first photo stands in (`Album.cover_photo`). The cover is
  the album's card in "All albums" and the image a chat shows for the album link.
- **Photos** are kept as they were uploaded, byte for byte (`gallery/images.py`): JPEG, PNG or WebP,
  checked to be a picture first. The photo page and "Download" serve that original; only a 1000px
  thumbnail, upright and without metadata, is made for the cards. Files go under
  `MEDIA_ROOT/gallery/<album>/`; deleting a photo deletes its files.
- **Limits**: `GALLERY_MAX_FILES_PER_UPLOAD` (30) and `GALLERY_MAX_UPLOAD_MB` (25), from the
  environment. A file that is not an image is reported and the rest of the batch is kept.
- **Pages**: `gallery_index` (newest album, others as tabs), `gallery_album`, `gallery_albums`
  (all albums by cover), `gallery_photo` (one photo, arrow keys step through the album).
- **Event page**: `calendar_app/detail.html` lists the event's public albums.
- **Search**: public albums are the `gallery` sitemap section; the index and the album list are in
  `sections`.

Tests: `tests/test_gallery.py`.
