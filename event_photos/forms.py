from django import forms
from django.utils.translation import gettext_lazy as _

from event_photos.dropbox import clean_folder_link, is_folder_link
from event_photos.index import is_valid_bib, normalize_bib
from event_photos.models import BIB_MAX_LENGTH, ExternalAlbum


class DeclaredBibForm(forms.Form):
    """The bib a member names for themselves at an event, read as an index's bib is."""

    bib = forms.CharField(
        label=_("My bib at this event"),
        max_length=BIB_MAX_LENGTH,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )

    def clean_bib(self):
        bib = normalize_bib(self.cleaned_data["bib"])
        if not is_valid_bib(bib):
            raise forms.ValidationError(_("A bib holds only letters, digits and other printable characters."))
        return bib


class ExternalAlbumForm(forms.ModelForm):
    class Meta:
        model = ExternalAlbum
        fields = ("folder_url", "title_ru", "title_kk", "title_en", "credit_ru", "credit_kk", "credit_en")
        help_texts = {  # noqa: RUF012
            "folder_url": _(
                'A Dropbox folder shared as "Anyone with the link can view", with photo-index.v1.json in it.'
            ),
        }

    def clean_folder_url(self):
        url = self.cleaned_data["folder_url"].strip()
        if not is_folder_link(url):
            raise forms.ValidationError(
                _(
                    "Paste a Dropbox shared folder link (https://www.dropbox.com/scl/fo/...). "
                    "Other services are not supported yet."
                )
            )
        return clean_folder_link(url)
