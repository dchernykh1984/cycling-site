from typing import ClassVar

from django import forms
from django.utils.translation import gettext_lazy as _

from knowledge.models import MAX_BODY_LENGTH, DraftSubmission, KnowledgeArticle

_TITLE_ATTRS = {"class": "form-control"}
_CATEGORY_ATTRS = {"class": "form-control"}


def _validate_body_length(value: str) -> str:
    if value and len(value) > MAX_BODY_LENGTH:
        raise forms.ValidationError(_("The article is too large. Use fewer or smaller inline images."))
    return value


class DraftSubmissionForm(forms.ModelForm):
    """Participant-facing knowledge submission. Body is rich HTML written by Quill into a
    hidden field; it is sanitized centrally when the submission is approved into a
    KnowledgeArticle (KnowledgeArticle.save())."""

    locale = forms.ChoiceField(
        choices=DraftSubmission.LOCALE_CHOICES, label=_("Locale"), widget=forms.Select(attrs={"class": "form-select"})
    )
    body = forms.CharField(widget=forms.HiddenInput(), label=_("Body"))

    class Meta:
        model = DraftSubmission
        fields: ClassVar[list] = ["locale", "title", "body", "category"]
        widgets: ClassVar[dict] = {
            "title": forms.TextInput(attrs=_TITLE_ATTRS),
            "category": forms.TextInput(attrs=_CATEGORY_ATTRS),
        }

    def clean_body(self):
        return _validate_body_length(self.cleaned_data.get("body") or "")


class KnowledgeArticleForm(forms.ModelForm):
    """Manager-facing create/edit form for a KnowledgeArticle. Body is rich HTML from Quill;
    sanitization happens in KnowledgeArticle.save()."""

    locale = forms.ChoiceField(
        choices=KnowledgeArticle.LOCALE_CHOICES, label=_("Locale"), widget=forms.Select(attrs={"class": "form-select"})
    )
    body = forms.CharField(required=False, widget=forms.HiddenInput(), label=_("Body"))

    class Meta:
        model = KnowledgeArticle
        fields: ClassVar[list] = ["locale", "title", "body", "category", "tags"]
        widgets: ClassVar[dict] = {
            "title": forms.TextInput(attrs=_TITLE_ATTRS),
            "category": forms.TextInput(attrs=_CATEGORY_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # taggit's TagField renders a plain text input; give it Bootstrap styling + a hint.
        self.fields["tags"].widget.attrs.update({"class": "form-control", "placeholder": _("comma,separated,tags")})
        self.fields["tags"].required = False

    def clean_body(self):
        return _validate_body_length(self.cleaned_data.get("body") or "")
