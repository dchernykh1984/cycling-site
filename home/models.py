from typing import ClassVar

from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import RichTextBlock
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_localize.fields import SynchronizedField


class HomePage(Page):
    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]


class AboutPage(Page):
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
