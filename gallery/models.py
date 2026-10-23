"""Photo albums: a named set of photos from a race, a ride or a camp, with one photo as its cover.

An album is created by an admin or the owner, may point at an event in the calendar (then the
event page links to it), and has a cover the person managing it picks -- the photo shown for the
album in the list of albums and in a link pasted into a chat. Until one is picked the first photo
stands in, so an album with photos never shows an empty frame.
"""

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager


class AlbumManager(MultilingualManager["Album"]):
    def public(self):
        return self.filter(is_hidden=False)

    def visible_to(self, user):
        from gallery.permissions import is_admin_plus

        if is_admin_plus(user):
            return self.all()
        if user.is_authenticated:
            return self.filter(models.Q(is_hidden=False) | models.Q(created_by=user))
        return self.public()


class Album(models.Model):
    title = models.CharField(_("Title"), max_length=200)
    date = models.DateField(_("Date"))
    competition = models.ForeignKey(
        "calendar_app.Competition",
        verbose_name=_("Event"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="albums",
    )
    cover = models.ForeignKey(
        "gallery.Photo",
        verbose_name=_("Cover photo"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    is_hidden = models.BooleanField(_("Hidden"), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AlbumManager()

    class Meta:
        ordering: ClassVar[list[str]] = ["-date", "-pk"]
        verbose_name = _("Album")
        verbose_name_plural = _("Albums")

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("gallery_album", args=[self.pk])

    @property
    def cover_photo(self):
        """The picked cover, or the first photo while none is picked; None for an empty album."""
        if self.cover_id:
            return self.cover
        return self.photos.first()


def _original_path(photo, filename):
    return f"gallery/{photo.album_id}/{filename}"


def _thumb_path(photo, filename):
    return f"gallery/{photo.album_id}/thumbs/{filename}"


class Photo(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="photos")
    # The size as shown (gallery.images.process), set by whoever saves the photo; not read back from the
    # file, whose pixels a phone may store lying on their side.
    image = models.ImageField(upload_to=_original_path)
    thumbnail = models.ImageField(upload_to=_thumb_path)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    caption = models.CharField(_("Caption"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "pk"]
        verbose_name = _("Photo")
        verbose_name_plural = _("Photos")

    def __str__(self) -> str:
        return self.caption or f"{self.album} #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("gallery_photo", args=[self.pk])

    @property
    def is_cover(self) -> bool:
        cover = self.album.cover_photo
        return cover is not None and cover.pk == self.pk
