import re

from django.core.exceptions import ValidationError
from wagtail.models import Locale

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


def live_page_in(model, locale):
    """``model``'s live page in ``locale``, else any live one: a language with no page of its own
    still links somewhere. None when there is no live page at all."""
    page = model.objects.live().filter(locale=locale).first() if locale is not None else None
    return page if page is not None else model.objects.live().first()


def active_locale_page_url(model) -> str | None:
    """The address of ``model``'s page in the active language, as the header links it.

    With no locale row for the active or the default language the link falls back to any live page,
    rather than failing every page that carries it (#385).
    """
    try:
        locale = Locale.get_active()
    except Locale.DoesNotExist:
        locale = None
    page = live_page_in(model, locale)
    return page.url if page else None
