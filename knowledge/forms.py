from typing import ClassVar

from django import forms
from django.utils.translation import gettext_lazy as _

from cycling_site.forms import LocalizedMaxLengthMixin
from cycling_site.richtext import validate_rich_text_length as _validate_body_length
from knowledge.models import DraftSubmission, KnowledgeArticle, KnowledgeArticleComment

_TITLE_ATTRS = {"class": "form-control"}
_CATEGORY_ATTRS = {"class": "form-control"}


class DraftSubmissionForm(LocalizedMaxLengthMixin, forms.ModelForm):
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


class AddKnowledgeArticleCommentForm(forms.ModelForm):
    """Reader comment on a KnowledgeArticle (mirrors calendar_app.AddCompetitionCommentForm)."""

    class Meta:
        model = KnowledgeArticleComment
        fields: ClassVar[list] = ["body"]
        widgets: ClassVar[dict] = {
            "body": forms.Textarea(
                attrs={"rows": 4, "placeholder": _("Write a comment..."), "class": "form-control w-100"}
            ),
        }


class KnowledgeArticleForm(LocalizedMaxLengthMixin, forms.ModelForm):
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
