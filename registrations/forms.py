import datetime
from typing import ClassVar

from django import forms

from .models import CompetitionRegistration, RegistrationCategory


class RegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    gender = forms.ChoiceField(choices=[("M", "M"), ("F", "F")], widget=forms.RadioSelect)
    birth_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    birth_year = forms.IntegerField(min_value=1900, max_value=datetime.date.today().year, required=False)
    category = forms.ModelChoiceField(queryset=RegistrationCategory.objects.none(), required=False)
    city = forms.CharField(max_length=100, required=False)
    team_name = forms.CharField(max_length=100, required=False, label="Team")
    additional_info = forms.CharField(
        max_length=100, required=False, widget=forms.TextInput(attrs={"maxlength": "100"})
    )

    def __init__(self, *args, competition=None, user=None, readonly_fields=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.competition = competition
        self._user = user
        self._readonly_fields = readonly_fields or []

        if competition:
            if competition.birth_date_mode == "year":
                self.fields["birth_year"].required = True
                del self.fields["birth_date"]
            else:
                del self.fields["birth_year"]

            if not competition.show_additional_info_field:
                del self.fields["additional_info"]

        for field_name in self._readonly_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs["readonly"] = True
                self.fields[field_name].widget.attrs["class"] = "form-control-plaintext"

    def clean(self):
        cleaned = super().clean()
        if self.competition and self.competition.birth_date_mode == "year":
            year = cleaned.get("birth_year")
            if year:
                cleaned["birth_date"] = datetime.date(year, 1, 1)
        return cleaned


class RejectRegistrationForm(forms.Form):
    rejection_note = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2}))


class EditRegistrationForm(forms.ModelForm):
    team_name = forms.CharField(max_length=100, required=False, label="Team")

    class Meta:
        model = CompetitionRegistration
        fields: ClassVar[list[str]] = [
            "first_name",
            "last_name",
            "birth_date",
            "gender",
            "category",
            "city",
            "additional_info",
            "is_approved",
            "is_paid",
        ]
        widgets: ClassVar[dict] = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "gender": forms.RadioSelect(choices=[("M", "M"), ("F", "F")]),
        }

    def __init__(self, *args, competition=None, service_fields_only=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.competition = competition
        if service_fields_only:
            keep = {"is_approved", "is_paid"}
            for name in list(self.fields.keys()):
                if name not in keep:
                    del self.fields[name]
        else:
            if competition:
                self.fields["category"].queryset = RegistrationCategory.objects.filter(
                    competition=competition, is_deleted=False
                )
