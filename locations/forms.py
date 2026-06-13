from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Location


class LocationForm(forms.Form):
    name_ru = forms.CharField(max_length=255, label=_("Name (RU)"))
    name_kk = forms.CharField(max_length=255, label=_("Name (KK)"), required=False)
    name_en = forms.CharField(max_length=255, label=_("Name (EN)"), required=False)
    parent = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label=_("Parent location"),
        empty_label=_("top level"),
    )
    lat = forms.DecimalField(max_digits=9, decimal_places=6, required=False, label=_("Latitude"))
    lng = forms.DecimalField(max_digits=9, decimal_places=6, required=False, label=_("Longitude"))
    is_hidden = forms.BooleanField(required=False, label=_("Hidden"))

    def __init__(self, *args, exclude_pk=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Location.objects.filter(is_deleted=False).order_by("path")
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        self.fields["parent"].queryset = qs
        self.fields["parent"].label_from_instance = lambda obj: (
            "--" * (obj.depth - 1) + " " + (obj.name or f"#{obj.pk}") if obj.depth > 1 else (obj.name or f"#{obj.pk}")
        )
