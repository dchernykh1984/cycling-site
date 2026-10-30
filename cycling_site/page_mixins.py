import re

from django.core.exceptions import ValidationError

_ASCII_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+\Z")
_LANGUAGE_PREFIX = re.compile(r"^/[a-z]{2}(?:-[a-z]+)?/")


class OwnLanguageUrlMixin:
    """Address a page under its own language's prefix.

    Each language's tree starts at a home page of the same url_path ("/home/"), so Wagtail matches
    every page to the first of the site's root paths, the default language's: a Kazakh or English
    page came out as /ru/..., and the menu sent those readers to the Russian knowledge base.
    """

    def get_url_parts(self, request=None):
        parts = super().get_url_parts(request)  # type: ignore[misc]
        if not parts or parts[2] is None:
            return parts
        site_id, root_url, path = parts
        return site_id, root_url, _LANGUAGE_PREFIX.sub(f"/{self.locale.language_code}/", path, count=1)  # type: ignore[attr-defined]


class AsciiSlugMixin:
    """Reject Cyrillic (and any non-ASCII) characters in page slugs.

    Apply before Page in the MRO so our check runs after Wagtail's
    own clean() has finished auto-populating the slug from the title.
    """

    def clean(self) -> None:
        super().clean()  # type: ignore[misc]
        if self.slug and not _ASCII_SLUG_RE.match(self.slug):  # type: ignore[attr-defined]
            raise ValidationError({"slug": "Slug must contain only Latin letters, numbers, hyphens, and underscores."})
