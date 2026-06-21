"""Shared form helpers."""

from django.utils.translation import gettext_lazy as _


class LocalizedMaxLengthMixin:
    """Replace Django's built-in ``max_length`` error message with a project-catalog string.

    Django's bundled Kazakh (kk) catalog lacks the length message, so it surfaced in Russian on
    the KK tab. Routing it through the project catalog gives a correctly translated message for
    every configured locale. Mix in before ``forms.Form``/``forms.ModelForm``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if getattr(field, "max_length", None):
                field.error_messages["max_length"] = _("Ensure this value has at most %(limit_value)d characters.")
