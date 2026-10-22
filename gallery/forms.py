import shutil
from pathlib import Path
from typing import ClassVar

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from calendar_app.models import Competition
from gallery.models import Album


class CompetitionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.date_start:%d.%m.%Y} - {obj.title}"


class AlbumForm(forms.ModelForm):
    """Title and date of an album, and the event it belongs to.

    With an event picked, an empty title or date is taken from the event, so "Gran Fondo Alatau" on
    23.10.2026 needs one choice instead of retyping. A title given by hand always wins.
    """

    title = forms.CharField(
        label=_("Title"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Gran Fondo 2026"}),
    )
    date = forms.DateField(
        label=_("Date"),
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    competition = CompetitionChoiceField(
        label=_("Event"),
        required=False,
        queryset=Competition.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=_("Optional. The album is linked from the event page; an empty title and date are taken from it."),
    )

    class Meta:
        model = Album
        fields = ("competition", "title", "date", "is_hidden")
        widgets: ClassVar[dict] = {"is_hidden": forms.CheckboxInput(attrs={"class": "form-check-input"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only events anybody may see: an album is public, and it takes its event's title -- an
        # invite-only or hidden event's name would surface in the gallery and the sitemap.
        self.fields["competition"].queryset = Competition.objects.filter(
            status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False, invite_only=False
        ).order_by("-date_start", "pk")

    def clean(self):
        data = super().clean()
        competition = data.get("competition")
        if competition is not None:
            if not data.get("title"):
                data["title"] = competition.title
            if not data.get("date"):
                data["date"] = competition.date_start
        if not data.get("title"):
            self.add_error("title", _("Give the album a title, or pick the event it belongs to."))
        if not data.get("date"):
            self.add_error("date", _("Give the album a date, or pick the event it belongs to."))
        return data


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        return [super(MultipleImageField, self).clean(item, initial) for item in files]


def max_files() -> int:
    return getattr(settings, "GALLERY_MAX_FILES_PER_UPLOAD", 30)


def max_file_mb() -> int:
    return getattr(settings, "GALLERY_MAX_UPLOAD_MB", 25)


def max_batch_mb() -> int:
    return getattr(settings, "GALLERY_MAX_BATCH_MB", 90)


def disk_reserve_mb() -> int:
    return getattr(settings, "GALLERY_DISK_RESERVE_MB", 200)


def free_media_bytes() -> int:
    """Free space on the disk MEDIA_ROOT is on, measured at its nearest folder that exists yet."""
    path = Path(settings.MEDIA_ROOT)
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path).free


class PhotoUploadForm(forms.Form):
    photos = MultipleImageField(
        label=_("Photos"),
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-control", "accept": "image/*", "multiple": True}),
    )

    def clean_photos(self):
        files = self.cleaned_data.get("photos") or []
        if len(files) > max_files():
            raise forms.ValidationError(
                _("At most %(count)d photos at a time; upload the rest in another go.") % {"count": max_files()}
            )
        limit = max_file_mb() * 1024 * 1024
        too_big = [f.name for f in files if f.size > limit]
        if too_big:
            raise forms.ValidationError(
                _("Larger than %(size)d MB: %(names)s") % {"size": max_file_mb(), "names": ", ".join(too_big)}
            )
        if sum(f.size for f in files) > max_batch_mb() * 1024 * 1024:
            raise forms.ValidationError(
                _("More than %(size)d MB at once; upload these photos in a few goes.") % {"size": max_batch_mb()}
            )
        # Originals are kept as they came, and the disk is the one every other upload uses too --
        # event posters, news pictures, protocols. The gallery never takes the last of it.
        reserve = disk_reserve_mb() * 1024 * 1024
        if files and free_media_bytes() - sum(f.size for f in files) < reserve:
            raise forms.ValidationError(
                _("Not enough room left on the site's disk for these photos. Ask the owner to make room.")
            )
        return files
