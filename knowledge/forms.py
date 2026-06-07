from typing import ClassVar

from django import forms

from knowledge.models import DraftSubmission


class DraftSubmissionForm(forms.ModelForm):
    locale = forms.ChoiceField(choices=DraftSubmission.LOCALE_CHOICES)

    class Meta:
        model = DraftSubmission
        fields: ClassVar[list] = ["locale", "title", "body", "category"]
        widgets: ClassVar[dict] = {
            "body": forms.Textarea(attrs={"rows": 10}),
        }
