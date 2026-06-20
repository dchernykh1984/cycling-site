from typing import ClassVar

from django import forms
from django.utils.translation import gettext_lazy as _

from cycling_site.richtext import validate_rich_text_length
from home.models import SiteContent


class SiteContentForm(forms.ModelForm):
    class Meta:
        model = SiteContent
        fields: ClassVar[list] = [
            "navbar_title_ru",
            "navbar_title_kk",
            "navbar_title_en",
            "page_title_ru",
            "page_title_kk",
            "page_title_en",
            "body_ru",
            "body_kk",
            "body_en",
        ]
        widgets: ClassVar[dict] = {
            "body_ru": forms.HiddenInput(attrs={"id": "id_body_ru"}),
            "body_kk": forms.HiddenInput(attrs={"id": "id_body_kk"}),
            "body_en": forms.HiddenInput(attrs={"id": "id_body_en"}),
            "navbar_title_ru": forms.TextInput(attrs={"class": "form-control"}),
            "navbar_title_kk": forms.TextInput(attrs={"class": "form-control"}),
            "navbar_title_en": forms.TextInput(attrs={"class": "form-control"}),
            "page_title_ru": forms.TextInput(attrs={"class": "form-control"}),
            "page_title_kk": forms.TextInput(attrs={"class": "form-control"}),
            "page_title_en": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels: ClassVar[dict] = {
            "navbar_title_ru": _("Navbar title (RU)"),
            "navbar_title_kk": _("Navbar title (KK)"),
            "navbar_title_en": _("Navbar title (EN)"),
            "page_title_ru": _("Tab title (RU)"),
            "page_title_kk": _("Tab title (KK)"),
            "page_title_en": _("Tab title (EN)"),
        }

    # Reject an oversized body per locale (inline images are base64); the body HTML itself is
    # sanitized centrally in SiteContent.save().
    def clean_body_ru(self):
        return validate_rich_text_length(self.cleaned_data.get("body_ru") or "")

    def clean_body_kk(self):
        return validate_rich_text_length(self.cleaned_data.get("body_kk") or "")

    def clean_body_en(self):
        return validate_rich_text_length(self.cleaned_data.get("body_en") or "")
