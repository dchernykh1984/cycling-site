"""Shared policy for stored rich-text (Quill HTML) bodies/descriptions.

A single size cap applied uniformly on every untrusted web + API write path (knowledge,
news, competitions). Inline images are embedded as base64 data URIs, so an unbounded value
would bloat the DB rows, API payloads and requests; without one shared limit the same HTML
is accepted on one path and rejected on another, and the cap can be bypassed via a laxer one.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

# Max characters for a single rich-text value (~1 MB; allows formatted text + a couple of
# modest inline images).
MAX_RICH_TEXT_LENGTH = 1_000_000


def is_too_large(value: str | None) -> bool:
    return value is not None and len(value) > MAX_RICH_TEXT_LENGTH


def validate_rich_text_length(value: str) -> str:
    """Form-field validator: reject an over-limit value with a localized message."""
    if is_too_large(value):
        raise forms.ValidationError(_("The text is too large. Use fewer or smaller inline images."))
    return value
