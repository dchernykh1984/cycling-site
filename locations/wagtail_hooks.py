from typing import ClassVar

from django import forms
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Location


class LocationForm(forms.ModelForm):
    parent = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label="Parent location",
        help_text="Leave empty for a top-level location (country).",
    )

    class Meta:
        model = Location
        fields: ClassVar[list] = ["parent", "name_ru", "name_kk", "name_en", "lat", "lng", "knowledge_article"]

    def save(self, commit=True):
        parent = self.cleaned_data.get("parent")
        instance = super().save(commit=False)
        if not instance.pk:
            kwargs = {
                "name_ru": instance.name_ru or "",
                "name_kk": instance.name_kk or "",
                "name_en": instance.name_en or "",
                "lat": instance.lat,
                "lng": instance.lng,
                "knowledge_article": instance.knowledge_article,
            }
            if parent:
                return parent.add_child(**kwargs)
            return Location.add_root(**kwargs)
        if commit:
            instance.save()
        return instance


class LocationViewSet(SnippetViewSet):
    model = Location
    list_display: ClassVar[list] = ["__str__", "depth", "lat", "lng", "knowledge_article"]
    search_fields: ClassVar[list] = ["name_ru", "name_kk", "name_en"]

    def get_form_class(self, for_update=False):
        return LocationForm


register_snippet(LocationViewSet)
