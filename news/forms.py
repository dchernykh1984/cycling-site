from typing import ClassVar

from django import forms

from knowledge.models import DraftSubmission
from news.models import Comment


class SubmitNewsForm(forms.ModelForm):
    locale = forms.ChoiceField(choices=DraftSubmission.LOCALE_CHOICES)

    class Meta:
        model = DraftSubmission
        fields: ClassVar[list] = ["locale", "title", "body"]
        widgets: ClassVar[dict] = {
            "body": forms.Textarea(attrs={"rows": 10}),
        }


class AddCommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields: ClassVar[list] = ["body"]
        widgets: ClassVar[dict] = {
            "body": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Write a comment...", "class": "form-control w-100"}
            ),
        }
