from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .models import ProtocolSection

_NAME_LENGTH = ProtocolSection._meta.get_field("name").max_length


class SectionNamesForm(forms.Form):
    """A protocol section's name in every language of the site, none of them left out (issue #452)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for code, language in settings.LANGUAGES:
            self.fields[code] = forms.CharField(label=_(language), max_length=_NAME_LENGTH)

    def names(self) -> dict[str, str]:
        return {code: self.cleaned_data[code] for code, _language in settings.LANGUAGES}
