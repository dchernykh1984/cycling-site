from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from gallery.forms import AlbumForm, PhotoUploadForm, max_batch_mb, max_file_mb, max_files
from gallery.images import PhotoError, process
from gallery.models import Album, Photo
from gallery.permissions import can_create_album, can_manage_album

#: Albums named in the row of tabs above the photos; the rest are one click away under "View more".
TABS = 5
PHOTOS_PER_PAGE = 48
ALBUMS_PER_PAGE = 24


def _visible_album(request, pk) -> Album:
    album = Album.objects.visible_to(request.user).filter(pk=pk).first()
    if album is None:
        raise Http404
    return album


def _share_image(request, album):
    cover = album.cover_photo if album else None
    if cover is None or not cover.thumbnail:
        return {}
    return {
        "og_image": request.build_absolute_uri(cover.image.url),
        "og_image_width": cover.width,
        "og_image_height": cover.height,
    }


def _album_page(request, album):
    albums = Album.objects.visible_to(request.user)
    tabs = list(albums[:TABS])
    if album is not None and album not in tabs:
        tabs = [album, *tabs[: TABS - 1]]
    photos = Paginator(album.photos.all(), PHOTOS_PER_PAGE).get_page(request.GET.get("page")) if album else None
    context = {
        "album": album,
        "tabs": tabs,
        "has_more_albums": albums.count() > len(tabs),
        "photos": photos,
        "can_create": can_create_album(request.user),
        "can_manage": album is not None and can_manage_album(request.user, album),
        "meta_title": f"{_('Gallery')}: {album.title}" if album else _("Gallery"),
        "meta_description": (
            _("Photos from %(title)s, %(date)s.") % {"title": album.title, "date": f"{album.date:%d.%m.%Y}"}
            if album
            else _("Photos from our races, rides and training camps.")
        ),
        **_share_image(request, album),
    }
    return render(request, "gallery/gallery.html", context)


def gallery_index(request):
    """The newest album, with the others as tabs: the page the navbar's "Gallery" opens."""
    return _album_page(request, Album.objects.visible_to(request.user).first())


def gallery_album(request, pk):
    return _album_page(request, _visible_album(request, pk))


def gallery_albums(request):
    albums = Album.objects.visible_to(request.user).select_related("cover").annotate(photo_count=Count("photos"))
    page = Paginator(albums, ALBUMS_PER_PAGE).get_page(request.GET.get("page"))
    return render(
        request,
        "gallery/albums.html",
        {
            "albums": page,
            "can_create": can_create_album(request.user),
            "meta_title": _("All albums"),
            "meta_description": _("Photos from our races, rides and training camps."),
        },
    )


def photo_detail(request, pk):
    photo = get_object_or_404(Photo.objects.select_related("album"), pk=pk)
    album = _visible_album(request, photo.album_id)
    ids = list(album.photos.values_list("pk", flat=True))
    position = ids.index(photo.pk)
    return render(
        request,
        "gallery/photo.html",
        {
            "album": album,
            "photo": photo,
            "position": position + 1,
            "total": len(ids),
            "previous_id": ids[position - 1] if position > 0 else None,
            "next_id": ids[position + 1] if position + 1 < len(ids) else None,
            "can_manage": can_manage_album(request.user, album),
            "meta_title": f"{album.title} - {position + 1}/{len(ids)}",
            "og_image": request.build_absolute_uri(photo.image.url),
            "og_image_width": photo.width,
            "og_image_height": photo.height,
        },
    )


def _save_uploads(request, album, files) -> int:
    saved, failed = 0, []
    start = (album.photos.aggregate(top=Max("sort_order"))["top"] or 0) + 1
    for offset, uploaded in enumerate(files):
        try:
            full, thumb = process(uploaded)
        except PhotoError as error:
            failed.append(f"{uploaded.name}: {error}")
            continue
        photo = Photo(album=album, sort_order=start + offset, uploaded_by=request.user)
        photo.image.save(full.name or "photo.jpg", full, save=False)
        photo.thumbnail.save(thumb.name or "photo.jpg", thumb, save=False)
        photo.save()
        saved += 1
    if failed:
        messages.warning(request, _("Not uploaded: %(files)s") % {"files": "; ".join(failed)})
    return saved


@login_required
def album_create(request):
    if not can_create_album(request.user):
        raise PermissionDenied
    form = AlbumForm(request.POST or None)
    upload = PhotoUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and upload.is_valid():
        with transaction.atomic():
            album = form.save(commit=False)
            album.created_by = request.user
            album.save()
        saved = _save_uploads(request, album, upload.cleaned_data["photos"])
        if saved:
            album.cover = album.photos.first()
            album.save(update_fields=["cover", "updated_at"])
        messages.success(request, _("Album created. Choose its cover photo below."))
        return redirect("gallery_album_edit", pk=album.pk)
    return render(
        request,
        "gallery/album_form.html",
        {
            "form": form,
            "upload": upload,
            "action": "create",
            "max_files": max_files(),
            "max_mb": max_file_mb(),
            "max_batch_mb": max_batch_mb(),
        },
    )


@login_required
def album_edit(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if not can_manage_album(request.user, album):
        raise PermissionDenied
    form = AlbumForm(request.POST or None, instance=album)
    upload = PhotoUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and upload.is_valid():
        album = form.save(commit=False)
        delete_ids = {int(value) for value in request.POST.getlist("delete") if value.isdigit()}
        for photo in album.photos.filter(pk__in=delete_ids):
            photo.delete()
        saved = _save_uploads(request, album, upload.cleaned_data["photos"])
        picked = request.POST.get("cover", "")
        picked_id = int(picked) if picked.isdigit() and int(picked) not in delete_ids else None
        if picked_id and album.photos.filter(pk=picked_id).exists():
            album.cover_id = picked_id
        elif album.cover_id is None or album.cover_id in delete_ids:
            album.cover = album.photos.first()
        album.save()
        if saved:
            messages.success(request, _("Photos uploaded: %(count)d.") % {"count": saved})
        else:
            messages.success(request, _("Album saved."))
        return redirect("gallery_album_edit", pk=album.pk)
    return render(
        request,
        "gallery/album_form.html",
        {
            "form": form,
            "upload": upload,
            "album": album,
            "photos": album.photos.all(),
            "cover": album.cover_photo,
            "action": "edit",
            "max_files": max_files(),
            "max_mb": max_file_mb(),
            "max_batch_mb": max_batch_mb(),
        },
    )


@login_required
@require_POST
def album_delete(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if not can_manage_album(request.user, album):
        raise PermissionDenied
    with transaction.atomic():
        album.cover = None
        album.save(update_fields=["cover"])
        for photo in album.photos.all():
            photo.delete()
        album.delete()
    messages.success(request, _("Album deleted."))
    return redirect("gallery_index")


@login_required
@require_POST
def photo_set_cover(request, pk):
    photo = get_object_or_404(Photo.objects.select_related("album"), pk=pk)
    if not can_manage_album(request.user, photo.album):
        raise PermissionDenied
    photo.album.cover = photo
    photo.album.save(update_fields=["cover", "updated_at"])
    messages.success(request, _("Cover photo changed."))
    return redirect(photo.get_absolute_url())
