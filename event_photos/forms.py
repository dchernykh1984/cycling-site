from django import forms
from django.utils.translation import gettext_lazy as _

from event_photos.dropbox import clean_folder_link, is_folder_link
from event_photos.models import ExternalAlbum


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
