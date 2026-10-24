"""The photo gallery over the API (issue #365): what the gallery's pages show, read the same way.

Anybody reads the albums they could open on the site -- a hidden album only admins and the owner --
and every photo in them, with its original and its card thumbnail. An album names its event only
while that event is public, as the album page does: a hidden or invite-only event's id would confirm
it exists.
"""

import datetime

from django.db.models import Count
from ninja import Router, Schema
from ninja.errors import HttpError

from api.auth import OptionalApiTokenAuth
from api.schemas import LocalizedStr, localize_field
from gallery.events import public_events
from gallery.models import Album, Photo
from gallery.permissions import is_admin_plus

optional_auth = OptionalApiTokenAuth()

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
