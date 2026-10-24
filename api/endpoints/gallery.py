"""The photo gallery over the API (issue #365): everything the gallery's pages do, by the same rules.

Anybody reads the albums they could open on the site -- a hidden album only admins and the owner --
and every photo in them, with its original and its card thumbnail. An album names its event only
while that event is public, as the album page does: a hidden or invite-only event's id would confirm
it exists.

Only admins and the owner change anything (gallery.permissions), as on the pages. An album's fields
go through the page's own AlbumForm -- an empty title or date taken from the linked event, only public
events offered -- and uploads through PhotoUploadForm's limits and gallery.actions, so a change made
here is exactly the one the pages would make.
"""

import datetime
from typing import Annotated

from django.db.models import Count
from django.utils.datastructures import MultiValueDict
from ninja import File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from pydantic import Field

from api.auth import ApiTokenAuth, OptionalApiTokenAuth
from api.schemas import LocalizedStr, localize_field
from gallery import actions
from gallery.events import public_events
from gallery.forms import AlbumForm, PhotoUploadForm
from gallery.models import Album, Photo
from gallery.permissions import can_create_album, can_manage_album, is_admin_plus

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()

# gallery.Photo.caption; tests/test_gallery_api.py checks it still matches the column.
MAX_CAPTION_LENGTH = 200
Caption = Annotated[str, Field(max_length=MAX_CAPTION_LENGTH)]

router = Router(tags=["gallery"])


class PhotoOut(Schema):
    id: int
    album_id: int
    caption: LocalizedStr
    width: int
    height: int
    sort_order: int
    image_url: str
    thumbnail_url: str

    @staticmethod
    def resolve_caption(obj: Photo) -> LocalizedStr:
        return localize_field(obj, "caption")

    @staticmethod
    def resolve_image_url(obj: Photo, context) -> str:
        return context["request"].build_absolute_uri(obj.image.url)

    @staticmethod
    def resolve_thumbnail_url(obj: Photo, context) -> str:
        return context["request"].build_absolute_uri(obj.thumbnail.url)


class AlbumOut(Schema):
    id: int
    title: LocalizedStr
    date: datetime.date
    competition_id: int | None
    cover_photo_id: int | None
    is_hidden: bool
    photo_count: int

    @staticmethod
    def resolve_title(obj: Album) -> LocalizedStr:
        return localize_field(obj, "title")

    @staticmethod
    def resolve_competition_id(obj: Album) -> int | None:
        return getattr(obj, "shown_competition_id", None)

    @staticmethod
    def resolve_cover_photo_id(obj: Album) -> int | None:
        cover = obj.cover_photo
        return cover.pk if cover else None

    @staticmethod
    def resolve_photo_count(obj: Album) -> int:
        count = getattr(obj, "photo_count", None)
        return count if count is not None else obj.photos.count()


class AlbumDetailOut(AlbumOut):
    photos: list[PhotoOut]

    @staticmethod
    def resolve_photos(obj: Album) -> list[Photo]:
        return list(obj.photos.all())


class LocalizedCaption(LocalizedStr):
    ru: Caption = ""
    kk: Caption = ""
    en: Caption = ""


class AlbumIn(Schema):
    title: LocalizedStr = LocalizedStr()
    date: datetime.date | None = None
    competition_id: int | None = None
    is_hidden: bool = False


class AlbumPatchIn(Schema):
    title: LocalizedStr | None = None
    date: datetime.date | None = None
    competition_id: int | None = None
    is_hidden: bool | None = None
    cover_photo_id: int | None = None


class PhotoPatchIn(Schema):
    caption: LocalizedCaption


class UploadOut(Schema):
    photos: list[PhotoOut]
    failed: list[str]


def _name_events(albums: list[Album], user) -> list[Album]:
    """Give each album the event id the reader may see: any to an admin, otherwise a public one only."""
    ids = {album.competition_id for album in albums if album.competition_id}
    shown = ids if is_admin_plus(user) else set(public_events().filter(pk__in=ids).values_list("pk", flat=True))
    for album in albums:
        album.shown_competition_id = album.competition_id if album.competition_id in shown else None  # type: ignore[attr-defined]
    return albums


def _visible_album(user, album_id: int) -> Album:
    album = Album.objects.visible_to(user).filter(pk=album_id).first()
    if album is None:
        raise HttpError(404, "Not found")
    return album


@router.get("/albums/", response=list[AlbumOut], auth=optional_auth, summary="List albums, newest first")
def list_albums(request):
    albums = list(Album.objects.visible_to(request.auth).select_related("cover").annotate(photo_count=Count("photos")))
    return _name_events(albums, request.auth)


@router.get("/albums/{album_id}", response=AlbumDetailOut, auth=optional_auth, summary="Get an album with its photos")
def get_album(request, album_id: int):
    return _name_events([_visible_album(request.auth, album_id)], request.auth)[0]


@router.get("/photos/{photo_id}", response=PhotoOut, auth=optional_auth, summary="Get a photo")
def get_photo(request, photo_id: int):
    photo = Photo.objects.filter(pk=photo_id).first()
    if photo is None:
        raise HttpError(404, "Not found")
    _visible_album(request.auth, photo.album_id)
    return photo


# -- Changing the gallery: admins and the owner only ------------------------------------------------

# The form's field names, as the API's payload calls them.
_PAYLOAD_NAMES = {
    "title_ru": "title.ru",
    "title_kk": "title.kk",
    "title_en": "title.en",
    "competition": "competition_id",
}


def _require_editor(user) -> None:
    if not can_create_album(user):
        raise HttpError(403, "Admin role is required")


def _album_to_change(user, album_id: int) -> Album:
    """The album, checked against the album rule the pages use (gallery.permissions.can_manage_album).

    Somebody who may change no album is refused before the lookup, so a 404 never tells them which
    albums -- hidden ones included -- exist.
    """
    _require_editor(user)
    album = Album.objects.filter(pk=album_id).first()
    if album is None:
        raise HttpError(404, "Not found")
    if not can_manage_album(user, album):
        raise HttpError(403, "Admin role is required")
    return album


def _photo_to_change(user, photo_id: int) -> Photo:
    _require_editor(user)
    photo = Photo.objects.select_related("album").filter(pk=photo_id).first()
    if photo is None:
        raise HttpError(404, "Not found")
    if not can_manage_album(user, photo.album):
        raise HttpError(403, "Admin role is required")
    return photo


def _valid_or_422(form) -> None:
    if not form.is_valid():
        raise HttpError(
            422,
            "; ".join(f"{_PAYLOAD_NAMES.get(name, name)}: {' '.join(errors)}" for name, errors in form.errors.items()),
        )


def _album_form(title: LocalizedStr, date, competition_id, is_hidden: bool, album: Album | None = None) -> AlbumForm:
    data = {
        "title_ru": title.ru,
        "title_kk": title.kk,
        "title_en": title.en,
        "date": date.isoformat() if date else "",
        "competition": competition_id or "",
        "is_hidden": is_hidden,
    }
    return AlbumForm(data, instance=album)


@router.post("/albums/", response={201: AlbumDetailOut}, auth=auth, summary="Create an album (admin)")
def create_album(request, payload: AlbumIn):
    """An empty title or date is taken from the linked event, as on the page; only public events may be linked."""
    _require_editor(request.auth)
    form = _album_form(payload.title, payload.date, payload.competition_id, payload.is_hidden)
    _valid_or_422(form)
    album = form.save(commit=False)
    album.created_by = request.auth
    album.save()
    return Status(201, _name_events([album], request.auth)[0])


@router.patch("/albums/{album_id}", response=AlbumDetailOut, auth=auth, summary="Change an album (admin)")
def update_album(request, album_id: int, payload: AlbumPatchIn):
    """Send only what changes. `title` replaces all three languages; `competition_id: null` unlinks the
    event; `cover_photo_id` picks one of the album's photos, `null` lets the first photo stand in."""
    album = _album_to_change(request.auth, album_id)
    data = payload.dict(exclude_unset=True)
    # The stored translations as they are, not filled in from one another: an empty one stays empty.
    stored = {language: getattr(album, f"title_{language}") or "" for language in ("ru", "kk", "en")}
    title = payload.title or LocalizedStr(**stored)
    form = _album_form(
        title,
        data["date"] if "date" in data else album.date,
        data["competition_id"] if "competition_id" in data else album.competition_id,
        data["is_hidden"] if data.get("is_hidden") is not None else album.is_hidden,
        album,
    )
    _valid_or_422(form)
    album = form.save(commit=False)
    if "cover_photo_id" in data:
        cover_id = data["cover_photo_id"]
        if cover_id is not None and not album.photos.filter(pk=cover_id).exists():
            raise HttpError(422, "cover_photo_id: not a photo of this album")
        album.cover_id = cover_id
    album.save()
    return _name_events([album], request.auth)[0]


@router.delete("/albums/{album_id}", response={204: None}, auth=auth, summary="Delete an album and its photos (admin)")
def delete_album(request, album_id: int):
    actions.delete_album(_album_to_change(request.auth, album_id))
    return Status(204, None)


@router.post(
    "/albums/{album_id}/photos/", response={201: UploadOut}, auth=auth, summary="Upload photos into an album (admin)"
)
def upload_photos(request, album_id: int, photos: list[UploadedFile] = File(...)):  # noqa: B008
    """Send the files as `photos` (multipart). The page's limits hold: the number of files, the size of
    each and of all together, and room left on the disk. A file that is not a picture is listed in
    `failed` and the rest are kept; when none could be kept the answer is 422."""
    album = _album_to_change(request.auth, album_id)
    files: MultiValueDict = MultiValueDict()
    files.setlist("photos", list(photos))
    form = PhotoUploadForm({}, files)
    _valid_or_422(form)
    saved, failed = actions.save_uploads(album, form.cleaned_data["photos"], request.auth)
    if not saved:
        raise HttpError(422, "; ".join(failed))
    actions.keep_a_cover(album)
    return Status(201, {"photos": saved, "failed": failed})


@router.patch("/photos/{photo_id}", response=PhotoOut, auth=auth, summary="Change a photo's caption (admin)")
def update_photo(request, photo_id: int, payload: PhotoPatchIn):
    photo = _photo_to_change(request.auth, photo_id)
    caption = payload.caption
    for language in ("ru", "kk", "en"):
        setattr(photo, f"caption_{language}", getattr(caption, language))
    # The canonical column directly: setattr through modeltranslation's descriptor would write into
    # the active language's column instead (as api/endpoints/content.py explains).
    photo.__dict__["caption"] = caption.ru or caption.kk or caption.en
    photo.save()
    return photo


@router.delete("/photos/{photo_id}", response={204: None}, auth=auth, summary="Delete a photo (admin)")
def delete_photo(request, photo_id: int):
    """The photo and its files go; an album that loses its cover shows its first photo instead."""
    actions.delete_photo(_photo_to_change(request.auth, photo_id))
    return Status(204, None)
