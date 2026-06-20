from typing import ClassVar

from django.core.cache import cache
from django.db import models
from django.utils.translation import get_language
from django.utils.translation import override as translation_override
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import RichTextBlock
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin
from cycling_site.sanitize import sanitize_rich_text_columns

_SITE_CONTENT_CACHE_KEY = "site_content_obj"


class SiteContent(models.Model):  # type: ignore[django-manager-missing]
    """Singleton model for editable site-wide text: navbar brand, home page title and body."""

    navbar_title = models.CharField(max_length=100, blank=True, verbose_name="Navbar title")
    page_title = models.CharField(max_length=200, blank=True, verbose_name="Page title")
    body = models.TextField(blank=True, verbose_name="Body")

    # Canonical + per-locale rich-text body columns (modeltranslation), sanitized on save.
    _BODY_FIELDS: ClassVar[tuple] = ("body", "body_ru", "body_kk", "body_en")

    class Meta:
        verbose_name = "Site content"

    def __str__(self) -> str:
        return "Site content"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        # Body is rich HTML rendered with |safe on the home page, so sanitize on every write
        # (the home-edit form is the only writer). See _BODY_FIELDS for the __dict__ rationale.
        sanitize_rich_text_columns(self, self._BODY_FIELDS, update_fields=kwargs.get("update_fields"))
        super().save(*args, **kwargs)
        cache.delete(_SITE_CONTENT_CACHE_KEY)

    @classmethod
    def load(cls) -> "SiteContent":
        obj = cache.get(_SITE_CONTENT_CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(_SITE_CONTENT_CACHE_KEY, obj, timeout=300)
        return obj


class LocalizedSiteContent:
    """Snapshot of SiteContent with fields pre-evaluated under a specific language.

    Wagtail's Page.serve() wraps template rendering in translation.override(page.locale),
    which overrides Django's request locale. Passing this snapshot instead of the raw
    SiteContent model ensures templates always see the URL-requested language, not the
    Wagtail page's own locale.
    """

    def __init__(self, sc: SiteContent, lang: str) -> None:
        with translation_override(lang):
            self.navbar_title: str = sc.navbar_title
            self.page_title: str = sc.page_title
            self.body: str = sc.body


class HomePage(AsciiSlugMixin, Page):
    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        # Use Django's request language (set by LocaleMiddleware from URL/cookie) rather
        # than get_language(), which Wagtail overrides to the page's own locale inside serve().
        lang = getattr(request, "LANGUAGE_CODE", None) or get_language()
        context["site_content"] = LocalizedSiteContent(SiteContent.load(), lang)
        return context


class AboutPage(AsciiSlugMixin, Page):
    body = StreamField(
        [("text", RichTextBlock())],
        blank=True,
        use_json_field=True,
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    content_panels: ClassVar[list] = [*Page.content_panels, FieldPanel("hero_image"), FieldPanel("body")]

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    class Meta:
        verbose_name = "About page"
