from django import forms

from locations.models import Location

from .models import CyclingDiscipline, EventType


class SubmitCompetitionForm(forms.Form):
    title = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}))
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
    )
    event_type: forms.ModelChoiceField[EventType] = forms.ModelChoiceField(
        queryset=EventType.objects.all(),
        required=False,
        empty_label="--",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    discipline: forms.ModelChoiceField[CyclingDiscipline] = forms.ModelChoiceField(
        queryset=CyclingDiscipline.objects.all(),
        required=False,
        empty_label="--",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    location: forms.ModelChoiceField[Location] = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        empty_label="--",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_start = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    date_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    url_announcement = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    url_registration = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    url_route = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    url_regulations = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    url_results = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))

    def clean(self):
        cleaned_data = super().clean()
        date_start = cleaned_data.get("date_start")
        date_end = cleaned_data.get("date_end")
        if date_start and date_end and date_end < date_start:
            raise forms.ValidationError("End date cannot be before start date.")
        return cleaned_data


class RejectCompetitionForm(forms.Form):
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control w-100"}),
    )


class CompetitionFilterForm(forms.Form):
    event_type = forms.ModelChoiceField(
        queryset=EventType.objects.all(),
        required=False,
        empty_label=None,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    discipline = forms.ModelChoiceField(
        queryset=CyclingDiscipline.objects.all(),
        required=False,
        empty_label=None,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        empty_label=None,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
