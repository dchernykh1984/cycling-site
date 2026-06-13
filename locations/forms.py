from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Location


class LocationForm(forms.Form):
    name_ru = forms.CharField(max_length=255, label=_("Name (RU)"))
    name_kk = forms.CharField(max_length=255, label=_("Name (KK)"), required=False)
    name_en = forms.CharField(max_length=255, label=_("Name (EN)"), required=False)
    city = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=True,
        label=_("City"),
        empty_label=None,
        widget=forms.HiddenInput(),
    )
    lat = forms.DecimalField(max_digits=9, decimal_places=6, required=False, label=_("Latitude"))
    lng = forms.DecimalField(max_digits=9, decimal_places=6, required=False, label=_("Longitude"))
    is_hidden = forms.BooleanField(required=False, label=_("Hidden"))

    def __init__(self, *args, exclude_pk=None, location_depth=4, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Location.objects.filter(is_deleted=False, depth=3).order_by("path")
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        self.fields["city"].queryset = qs
        self.fields["city"].required = location_depth >= 4
