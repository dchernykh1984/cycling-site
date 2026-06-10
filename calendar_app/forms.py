import json
from typing import ClassVar

from django import forms
from django.utils.translation import gettext_lazy as _

from locations.models import Location

from .models import Competition, CompetitionComment, Discipline, DisciplineCategory, EventType


class SubmitCompetitionForm(forms.Form):
    title_ru = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}))
    title_kk = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    title_en = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    description_ru = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
    )
    description_kk = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
    )
    description_en = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
    )
    event_type: forms.ModelChoiceField[EventType] = forms.ModelChoiceField(
        queryset=EventType.objects.all(),
        required=False,
        empty_label="--",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    discipline_category: forms.ModelChoiceField[DisciplineCategory] = forms.ModelChoiceField(
        queryset=DisciplineCategory.objects.all(),
        required=False,
        empty_label="--",
        label=_("Direction"),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_discipline_category"}),
    )
    discipline: forms.ModelChoiceField[Discipline] = forms.ModelChoiceField(
        queryset=Discipline.objects.select_related("category"),
        required=False,
        empty_label="--",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_discipline"}),
    )
    location: forms.ModelChoiceField[Location] = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_deleted=False),
        required=False,
        empty_label="--",
        widget=forms.HiddenInput(),
    )
    date_start = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
    )
    date_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
    )
    url_announcement = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    file_announcement = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
    url_registration = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    url_route = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    file_route = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
    url_regulations = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    file_regulations = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
    url_results = forms.URLField(required=False, widget=forms.URLInput(attrs={"class": "form-control"}))
    file_results = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))

    _MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
    _ALLOWED_EXTENSIONS: ClassVar[frozenset[str]] = frozenset(
        {"pdf", "doc", "docx", "xls", "xlsx", "gpx", "kml", "jpg", "jpeg", "png", "gif", "webp"}
    )

    def _validate_file(self, f):
        if not f:
            return f
        if f.size > self._MAX_FILE_BYTES:
            raise forms.ValidationError(_("File size must not exceed 10 MB."))
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in self._ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(self._ALLOWED_EXTENSIONS))
            raise forms.ValidationError(_("Unsupported file type. Allowed: %(allowed)s.") % {"allowed": allowed})
        return f

    def clean_file_announcement(self):
        return self._validate_file(self.cleaned_data.get("file_announcement"))

    def clean_file_route(self):
        return self._validate_file(self.cleaned_data.get("file_route"))

    def clean_file_regulations(self):
        return self._validate_file(self.cleaned_data.get("file_regulations"))

    def clean_file_results(self):
        return self._validate_file(self.cleaned_data.get("file_results"))

    def clean(self):
        cleaned_data = super().clean()
        date_start = cleaned_data.get("date_start")
        date_end = cleaned_data.get("date_end")
        if date_start and date_end and date_end < date_start:
            raise forms.ValidationError("End date cannot be before start date.")
        return cleaned_data


class RegistrationSettingsForm(forms.Form):
    registration_enabled = forms.BooleanField(required=False)
    registration_mode = forms.ChoiceField(
        choices=Competition.RegistrationMode.choices,
        required=False,
        widget=forms.RadioSelect,
    )
    birth_date_mode = forms.ChoiceField(
        choices=Competition.BirthDateMode.choices,
        required=False,
        widget=forms.RadioSelect,
    )
    require_approval = forms.BooleanField(required=False)
    require_payment = forms.BooleanField(required=False)
    allow_multiple_registrations = forms.BooleanField(required=False)
    registration_deadline = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
    )
    max_participants = forms.IntegerField(
        required=False, min_value=1, widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    show_unapproved_in_list = forms.BooleanField(required=False)
    show_unpaid_in_list = forms.BooleanField(required=False)
    show_approval_status_col = forms.BooleanField(required=False)
    show_payment_status_col = forms.BooleanField(required=False)
    show_additional_info_field = forms.BooleanField(required=False)
    relay_enabled = forms.BooleanField(required=False)
    relay_max_members = forms.IntegerField(
        required=False,
        min_value=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "style": "width:80px;"}),
    )
    categories_json = forms.CharField(required=False, widget=forms.HiddenInput)

    def get_categories(self) -> list[dict]:
        raw = self.cleaned_data.get("categories_json", "")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []


class AddCompetitionCommentForm(forms.ModelForm):
    body = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Write a comment...", "class": "form-control w-100"}),
    )

    class Meta:
        model = CompetitionComment
        fields: ClassVar[list] = ["body"]


class RejectCompetitionForm(forms.Form):
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control w-100"}),
    )


class CompetitionFilterForm(forms.Form):
    event_type = forms.ModelChoiceField(
        queryset=EventType.objects.all(),
        required=False,
        empty_label="-",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    discipline_category = forms.ModelChoiceField(
        queryset=DisciplineCategory.objects.all(),
        required=False,
        empty_label="-",
        widget=forms.Select(attrs={"class": "form-select form-select-sm", "id": "filter-direction"}),
    )
    discipline = forms.ModelChoiceField(
        queryset=Discipline.objects.select_related("category"),
        required=False,
        empty_label="-",
        widget=forms.Select(attrs={"class": "form-select form-select-sm", "id": "filter-discipline"}),
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_deleted=False),
        required=False,
        empty_label="-",
        widget=forms.HiddenInput(),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
