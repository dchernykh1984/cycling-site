from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Level, Location, location_subtree_is_nonempty, point_is_whole, selectable_parent_locations

# A place's point is the two numbers together: one alone pins nothing.
BOTH_OR_NEITHER = _("Give both the latitude and the longitude, or neither.")


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
    lat = forms.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False, label=_("Latitude")
    )
    lng = forms.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180, required=False, label=_("Longitude")
    )
    is_hidden = forms.BooleanField(required=False, label=_("Hidden"))

    def __init__(
        self, *args, exclude_pk=None, instance=None, user=None, can_manage=False, can_propose_place=False, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.can_manage = can_manage
        # Organizer+: may propose a region or a city, which then waits for a moderator.
        self.can_propose_place = can_propose_place
        # Only public nodes (or the user's own pending proposal) are pickable as a parent, so a
        # foreign pending node can't be used via the UI or a hand-crafted POST.
        qs = selectable_parent_locations(user)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        self.fields["parent"].queryset = qs

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        new_depth = parent.depth + 1 if parent is not None else Level.COUNTRY
        # A venue is open to everyone; a region or a city may be proposed by an organizer and a
        # country stays admin-only. Surface a clear field error for an incomplete cascade instead of
        # letting it fall through to the view's 403 guard (which stays as defense against a forged
        # POST).
        if not self.can_manage and (
            new_depth == Level.COUNTRY or (new_depth in (Level.REGION, Level.CITY) and not self.can_propose_place)
        ):
            raise forms.ValidationError(
                _("Select a country, region and city: a venue is added inside the chosen city.")
            )
        if self.instance is None:
            return parent
        if self.instance.is_system_fallback:
            current_parent = self.instance.get_parent()
            current_parent_id = current_parent.pk if current_parent is not None else None
            if getattr(parent, "pk", None) != current_parent_id:
                raise forms.ValidationError(_("System fallback locations cannot be moved."))
        # The chosen parent must not be the location itself or one of its descendants -- that
        # would make a node its own ancestor (a treebeard cycle).
        if parent is not None and (parent.pk == self.instance.pk or parent.is_descendant_of(self.instance)):
            raise forms.ValidationError(_("A location cannot be placed inside itself."))
        # Changing a node's level moves its whole subtree (children jump levels, venues stop
        # being depth-4) and orphans competitions that require a depth-4 venue. Forbid the level
        # change while the node has any physical subtree (even soft-deleted, which still moves)
        # or competitions in that subtree.
        new_depth = parent.depth + 1 if parent is not None else Level.COUNTRY
        if new_depth != self.instance.depth and location_subtree_is_nonempty(self.instance):
            raise forms.ValidationError(
                _("This location has nested locations or events, so its level cannot be changed.")
            )
        return parent

    def clean(self):
        cleaned = super().clean()
        if (
            "lat" not in self.errors
            and "lng" not in self.errors
            and not point_is_whole(cleaned.get("lat"), cleaned.get("lng"))
        ):
            raise forms.ValidationError(BOTH_OR_NEITHER)
        return cleaned

    def clean_is_hidden(self):
        is_hidden = self.cleaned_data.get("is_hidden", False)
        if self.instance is not None and self.instance.is_system_fallback and not is_hidden:
            raise forms.ValidationError(_("System fallback locations must remain hidden."))
        return is_hidden
