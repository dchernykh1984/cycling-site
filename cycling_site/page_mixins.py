import re

from django.core.exceptions import ValidationError

_ASCII_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+\Z")


class AsciiSlugMixin:
    """Reject Cyrillic (and any non-ASCII) characters in page slugs.

    Apply before Page in the MRO so our check runs after Wagtail's
    own clean() has finished auto-populating the slug from the title.
    """

    def clean(self) -> None:
        super().clean()  # type: ignore[misc]
        if self.slug and not _ASCII_SLUG_RE.match(self.slug):  # type: ignore[attr-defined]
            raise ValidationError({"slug": "Slug must contain only Latin letters, numbers, hyphens, and underscores."})
