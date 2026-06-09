from typing import ClassVar

from django import forms
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from knowledge.models import DraftSubmission
from news.models import Comment, NewsArticle


class SubmitNewsForm(forms.ModelForm):
    locale = forms.ChoiceField(choices=DraftSubmission.LOCALE_CHOICES)

    class Meta:
        model = DraftSubmission
        fields: ClassVar[list] = ["locale", "title", "body"]
        widgets: ClassVar[dict] = {
            "body": forms.Textarea(attrs={"rows": 10}),
        }


_BODY_ATTRS = {"rows": 10, "class": "form-control quill-source"}
_TITLE_ATTRS = {"class": "form-control"}
_INTRO_ATTRS = {"rows": 3, "class": "form-control"}


class NewsArticleForm(forms.ModelForm):
    title_ru = forms.CharField(
        max_length=255, label=format_lazy("{} (RU)", _("Title")), widget=forms.TextInput(attrs=_TITLE_ATTRS)
    )
    title_kk = forms.CharField(
        max_length=255,
        required=False,
        label=format_lazy("{} (KK)", _("Title")),
        widget=forms.TextInput(attrs=_TITLE_ATTRS),
    )
    title_en = forms.CharField(
        max_length=255,
        required=False,
        label=format_lazy("{} (EN)", _("Title")),
        widget=forms.TextInput(attrs=_TITLE_ATTRS),
    )
    intro_ru = forms.CharField(
        max_length=500,
        required=False,
        label=format_lazy("{} (RU)", _("Short description")),
        widget=forms.Textarea(attrs=_INTRO_ATTRS),
    )
    intro_kk = forms.CharField(
        max_length=500,
        required=False,
        label=format_lazy("{} (KK)", _("Short description")),
        widget=forms.Textarea(attrs=_INTRO_ATTRS),
    )
    intro_en = forms.CharField(
        max_length=500,
        required=False,
        label=format_lazy("{} (EN)", _("Short description")),
        widget=forms.Textarea(attrs=_INTRO_ATTRS),
    )
    body_ru = forms.CharField(required=False, label=format_lazy("{} (RU)", _("Body")), widget=forms.HiddenInput())
    body_kk = forms.CharField(required=False, label=format_lazy("{} (KK)", _("Body")), widget=forms.HiddenInput())
    body_en = forms.CharField(required=False, label=format_lazy("{} (EN)", _("Body")), widget=forms.HiddenInput())

    class Meta:
        model = NewsArticle
        fields: ClassVar[list] = [
            "title_ru",
            "title_kk",
            "title_en",
            "intro_ru",
            "intro_kk",
            "intro_en",
            "body_ru",
            "body_kk",
            "body_en",
            "hero_image",
            "published_at",
        ]
        widgets: ClassVar[dict] = {
            "published_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
            ),
            "hero_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
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
