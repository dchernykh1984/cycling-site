"""Shared form helpers."""

from django import forms
from django.contrib import messages
from django.utils.translation import gettext
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


def comment_widget() -> forms.Textarea:
    """The box a reader writes a comment in, on an event, a knowledge article or a news item."""
    return forms.Textarea(attrs={"rows": 4, "placeholder": _("Write a comment..."), "class": "form-control w-100"})


def flash_first_error(request, form) -> None:
    """Tell the member the first thing wrong with ``form``, for a form that posts back to its own page."""
    first_errors: list = next(iter(form.errors.values()), [])
    messages.error(request, first_errors[0] if first_errors else gettext("Invalid submission."))


def save_comment(request, form, **target) -> None:
    """Save ``form``'s comment as the member's on ``target`` (``article=...``), or say what was wrong."""
    if not form.is_valid():
        flash_first_error(request, form)
        return
    comment = form.save(commit=False)
    for field, value in target.items():
        setattr(comment, field, value)
    comment.author = request.user
    comment.save()
