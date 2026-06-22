from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Location, location_subtree_is_nonempty, selectable_parent_locations


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

    def __init__(self, *args, exclude_pk=None, instance=None, user=None, can_manage=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.can_manage = can_manage
        # Only public nodes (or the user's own pending proposal) are pickable as a parent, so a
        # foreign pending node can't be used via the UI or a hand-crafted POST.
        qs = selectable_parent_locations(user)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        self.fields["parent"].queryset = qs

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        new_depth = parent.depth + 1 if parent is not None else 1
        # Non-managers may only add a depth-4 venue under a city. Surface a clear field error for an
        # incomplete cascade instead of letting it fall through to the view's 403 authorization guard
        # (which stays as defense against a forged POST).
        if not self.can_manage and new_depth != 4:
            raise forms.ValidationError(
                _("Select a country, region and city: a venue is added inside the chosen city.")
            )
        if self.instance is None:
            return parent
        # The chosen parent must not be the location itself or one of its descendants -- that
        # would make a node its own ancestor (a treebeard cycle).
        if parent is not None and (parent.pk == self.instance.pk or parent.is_descendant_of(self.instance)):
            raise forms.ValidationError(_("A location cannot be placed inside itself."))
        # Changing a node's level moves its whole subtree (children jump levels, venues stop
        # being depth-4) and orphans competitions that require a depth-4 venue. Forbid the level
        # change while the node has any physical subtree (even soft-deleted, which still moves)
        # or competitions in that subtree.
        new_depth = parent.depth + 1 if parent is not None else 1
        if new_depth != self.instance.depth and location_subtree_is_nonempty(self.instance):
            raise forms.ValidationError(
                _("This location has nested locations or competitions, so its level cannot be changed.")
            )
        return parent
