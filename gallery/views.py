from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from gallery.actions import delete_album, keep_a_cover, save_uploads
from gallery.events import RESULT_LIMIT, describe_events, matching_ids, public_events
from gallery.forms import AlbumForm, PhotoUploadForm, max_batch_mb, max_file_mb, max_files
from gallery.images import THUMB_SIDE
from gallery.models import Album, Photo
from gallery.permissions import can_create_album, can_manage_album

#: Albums named in the row of tabs above the photos; the rest are one click away under "View more".
TABS = 5
PHOTOS_PER_PAGE = 48
ALBUMS_PER_PAGE = 24


def _selected_event(form):
    event = form.selected_event
    events = describe_events(public_events().filter(pk=event.pk)) if event else []
    return events[0] if events else None


def _linked_event(album):
    if album is None or album.competition_id is None:
        return None
    events = describe_events(public_events().filter(pk=album.competition_id))
    return events[0] if events else None


@login_required
@require_GET
@never_cache
def event_choices(request):
    if not can_create_album(request.user):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    if len(query) > 200:
        return JsonResponse({"error": _("Search text is too long.")}, status=400)
    ids = matching_ids(query)
    return JsonResponse(
        {
            "results": describe_events(public_events().filter(pk__in=ids[:RESULT_LIMIT])),
            "has_more": len(ids) > RESULT_LIMIT,
        }
    )


def _visible_album(request, pk) -> Album:
    album = Album.objects.visible_to(request.user).filter(pk=pk).first()
    if album is None:
        raise Http404
    return album


def _share_image(request, photo):
    """The picture a chat shows for a link: the thumbnail, never the original.

    An original may be 25 MB, and messengers skip a preview image of more than a few megabytes --
    the link would arrive bare. The thumbnail is the same shot, upright, at most THUMB_SIDE wide.
    """
    if photo is None or not photo.thumbnail:
        return {}
    scale = min(1.0, THUMB_SIDE / max(photo.width, photo.height, 1))
    return {
        "og_image": request.build_absolute_uri(photo.thumbnail.url),
        "og_image_width": round(photo.width * scale),
        "og_image_height": round(photo.height * scale),
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
        "linked_event": _linked_event(album),
        "meta_title": f"{_('Gallery')}: {album.title}" if album else _("Gallery"),
        "meta_description": (
            _("Photos from %(title)s, %(date)s.") % {"title": album.title, "date": f"{album.date:%d.%m.%Y}"}
            if album
            else _("Photos from our races, rides and training camps.")
        ),
        **_share_image(request, album.cover_photo if album else None),
    }
    return render(request, "gallery/gallery.html", context)


def gallery_index(request):
    """Every album the reader may see, newest first, by its cover: the page "Gallery" opens."""
    albums = Album.objects.visible_to(request.user).select_related("cover").annotate(photo_count=Count("photos"))
    page = Paginator(albums, ALBUMS_PER_PAGE).get_page(request.GET.get("page"))
    newest = albums.first()
    return render(
        request,
        "gallery/albums.html",
        {
            "albums": page,
            "can_create": can_create_album(request.user),
            "meta_title": _("Gallery"),
            "meta_description": _("Photos from our races, rides and training camps."),
            **_share_image(request, newest.cover_photo if newest else None),
        },
    )


def gallery_album(request, pk):
    return _album_page(request, _visible_album(request, pk))


def gallery_albums(request):
    """The list's former address, kept for links already shared: the gallery itself is the list."""
    query = request.GET.urlencode()
    return redirect(reverse("gallery_index") + (f"?{query}" if query else ""), permanent=True)


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
            **_share_image(request, photo),
        },
    )


def _save_uploads(request, album, files) -> int:
    saved, failed = save_uploads(album, files, request.user)
    if failed:
        messages.warning(request, _("Not uploaded: %(files)s") % {"files": "; ".join(failed)})
    return len(saved)


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
        _save_uploads(request, album, upload.cleaned_data["photos"])
        keep_a_cover(album)
        messages.success(request, _("Album created. Choose its cover photo below."))
        return redirect("gallery_album_edit", pk=album.pk)
    return render(
        request,
        "gallery/album_form.html",
        {
            "form": form,
            "upload": upload,
            "action": "create",
            "selected_event": _selected_event(form),
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
        delete_ids = {int(value) for value in request.POST.getlist("delete") if value.isdecimal()}
        for photo in album.photos.filter(pk__in=delete_ids):
            photo.delete()
        saved = _save_uploads(request, album, upload.cleaned_data["photos"])
        picked = request.POST.get("cover", "")
        picked_id = int(picked) if picked.isdecimal() and int(picked) not in delete_ids else None
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
            "selected_event": _selected_event(form),
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
    delete_album(album)
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
