from typing import ClassVar

from django.core.cache import cache
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import RichTextBlock
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin

_SITE_CONTENT_CACHE_KEY = "site_content_obj"


class SiteContent(models.Model):  # type: ignore[django-manager-missing]
    """Singleton model for editable site-wide text: navbar brand, home page title and body."""

    navbar_title = models.CharField(max_length=100, blank=True, verbose_name="Navbar title")
    page_title = models.CharField(max_length=200, blank=True, verbose_name="Page title")
    body = models.TextField(blank=True, verbose_name="Body")

    class Meta:
        verbose_name = "Site content"

    def __str__(self) -> str:
        return "Site content"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(_SITE_CONTENT_CACHE_KEY)

    @classmethod
    def load(cls) -> "SiteContent":
        obj = cache.get(_SITE_CONTENT_CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(_SITE_CONTENT_CACHE_KEY, obj, timeout=300)
        return obj


class HomePage(AsciiSlugMixin, Page):
    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["site_content"] = SiteContent.load()
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
