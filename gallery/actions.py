"""What changing an album does, written once for the gallery's pages and its API.

Both doors store an upload the same way, keep an album with photos from showing an empty cover, and
take an album's files with it when it goes -- so a photo added or removed through the API is exactly
the photo the pages would have made or removed.
"""

from django.db import transaction
from django.db.models import Max

from gallery.images import PhotoError, process
from gallery.models import Album, Photo


def save_uploads(album: Album, files, user) -> tuple[list[Photo], list[str]]:
    """Store every file that proves to be a picture, after the album's last photo.

    Returns the photos made and, for each file refused, "name: reason" -- one bad file does not
    stop the rest.
    """
    saved: list[Photo] = []
    failed: list[str] = []
    start = (album.photos.aggregate(top=Max("sort_order"))["top"] or 0) + 1
    for offset, uploaded in enumerate(files):
        try:
            full, thumb, (width, height) = process(uploaded)
        except PhotoError as error:
            failed.append(f"{uploaded.name}: {error}")
            continue
        photo = Photo(album=album, sort_order=start + offset, uploaded_by=user, width=width, height=height)
        photo.image.save(full.name or "photo.jpg", full, save=False)
        photo.thumbnail.save(thumb.name or "photo.jpg", thumb, save=False)
        photo.save()
        saved.append(photo)
    return saved, failed


def keep_a_cover(album: Album) -> None:
    """An album with photos and no cover takes its first photo, as a new album does."""
    if album.cover_id is None:
        first = album.photos.first()
        if first is not None:
            album.cover = first
            album.save(update_fields=["cover", "updated_at"])


def delete_album(album: Album) -> None:
    """Remove an album with every photo and file in it."""
    with transaction.atomic():
        album.cover = None
        album.save(update_fields=["cover"])
        for photo in album.photos.all():
            photo.delete()
        album.delete()
