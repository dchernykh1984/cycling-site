from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Location


class LocationForm(forms.Form):
    name_ru = forms.CharField(max_length=255, label=_("Name (RU)"))
    name_kk = forms.CharField(max_length=255, label=_("Name (KK)"), required=False)
    name_en = forms.CharField(max_length=255, label=_("Name (EN)"), required=False)
    # The deepest selected node in the country/region/city cascade. Empty means the new
    # location is itself a country (a depth-1 root); the level is always parent.depth + 1.
    parent = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label=_("Parent location"),
        widget=forms.HiddenInput(),
    )
    lat = forms.DecimalField(max_digits=9, decimal_places=6, required=False, label=_("Latitude"))
    lng = forms.DecimalField(max_digits=9, decimal_places=6, required=False, label=_("Longitude"))
    is_hidden = forms.BooleanField(required=False, label=_("Hidden"))

    def __init__(self, *args, exclude_pk=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        qs = Location.objects.filter(is_deleted=False, depth__in=[1, 2, 3]).order_by("path")
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        self.fields["parent"].queryset = qs

    def clean_parent(self):
        # When editing, the chosen parent must not be the location itself or one of its
        # descendants -- that would make a node its own ancestor (a treebeard cycle).
        parent = self.cleaned_data.get("parent")
        if parent is not None and self.instance is not None:
            if parent.pk == self.instance.pk or parent.is_descendant_of(self.instance):
                raise forms.ValidationError(_("A location cannot be placed inside itself."))
        return parent
