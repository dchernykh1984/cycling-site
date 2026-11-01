from html import unescape
from typing import ClassVar

from django.core.cache import cache
from django.db import models
from django.utils.html import strip_tags
from django.utils.translation import get_language
from django.utils.translation import override as translation_override
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import RichTextBlock
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin, OwnLanguageUrlMixin
from cycling_site.sanitize import sanitize_rich_text_columns

_SITE_CONTENT_CACHE_KEY = "site_content_obj"
# How long the site's texts and the About link are kept in the cache before being read again.
CACHE_SECONDS = 300
LANGUAGES = ("ru", "kk", "en")


class SiteContent(models.Model):  # type: ignore[django-manager-missing]
    """Singleton model for editable site-wide text: the navbar brand and the home page's title.

    The home page's text is its cards (HomeCard).
    """

    navbar_title = models.CharField(max_length=100, blank=True, verbose_name="Navbar title")
    page_title = models.CharField(max_length=200, blank=True, verbose_name="Page title")

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
            cache.set(_SITE_CONTENT_CACHE_KEY, obj, timeout=CACHE_SECONDS)
        return obj


def blank_rich_text(html: str) -> bool:
    """True for rich text with nothing to read or see in it, such as an editor left empty.

    Entities are read first: a "&nbsp;" is as empty as the space it stands for.
    """
    return not unescape(strip_tags(html)).strip() and "<img" not in html


class HomeCard(models.Model):  # type: ignore[django-manager-missing]
    """One card of the home page: a heading and the owner's rich text under it, in each language.

    The owner adds as many as they like and puts them in order. Every skin draws them as tiles in a
    grid: the site's own skins as cards in their colours, UBT Almaty in its own style.
    """

    title = models.CharField(max_length=255, blank=True, verbose_name="Title")
    body = models.TextField(blank=True, verbose_name="Body")
    position = models.PositiveIntegerField(default=0, verbose_name="Position")

    _BODY_FIELDS: ClassVar[tuple] = ("body", "body_ru", "body_kk", "body_en")

    class Meta:
        ordering = ("position", "pk")
        verbose_name = "Home card"

    def __str__(self) -> str:
        return self.title or "Home card"

    def save(self, *args, **kwargs) -> None:
        values = self.__dict__
        for lang in LANGUAGES:
            # An empty editor still sends "<p><br></p>", which would keep the reader from the
            # language the site falls back to; stored as nothing instead.
            if blank_rich_text(values.get(f"body_{lang}") or ""):
                values[f"body_{lang}"] = ""
        # The plain column holds the first language written, whoever wrote the card, as the API's
        # writes keep it for news and events; the API's localized fields fall back to it.
        for field in ("title", "body"):
            written = [values.get(f"{field}_{lang}") for lang in LANGUAGES]
            values[field] = next((value for value in written if value), "")
        # Rendered with |safe on the home page, like the text it replaced: sanitized on every write.
        sanitize_rich_text_columns(self, self._BODY_FIELDS, update_fields=kwargs.get("update_fields"))
        super().save(*args, **kwargs)

    @classmethod
    def next_position(cls) -> int:
        """The position after the last card: where a new one goes."""
        last = cls.objects.aggregate(last=models.Max("position"))["last"]
        return 0 if last is None else last + 1

    def delete(self, using=None, keep_parents=False):
        deleted = super().delete(using=using, keep_parents=keep_parents)
        # The others close up, so a card's position stays its place in the order, as the API reads it.
        HomeCard._number(HomeCard.objects.all())
        return deleted

    def place(self, index: int) -> None:
        """Move this saved card to `index` in the home page's order (clamped to either end)."""
        cards = list(HomeCard.objects.exclude(pk=self.pk))
        cards.insert(max(0, min(index, len(cards))), self)
        HomeCard._number(cards)

    @staticmethod
    def _number(cards) -> None:
        """Number the cards 0, 1, 2... in the order given."""
        for position, card in enumerate(cards):
            if card.position != position:
                HomeCard.objects.filter(pk=card.pk).update(position=position)
                card.position = position


def localized_cards(lang: str) -> list[dict[str, str]]:
    """The home page's cards as `lang` reads them, fallbacks included, leaving out any with nothing to show.

    Read under `lang` for the reason LocalizedSiteContent gives.
    """
    with translation_override(lang):
        cards = [{"title": card.title, "body": card.body} for card in HomeCard.objects.all()]
    return [card for card in cards if card["title"] or card["body"]]


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


class HomePage(OwnLanguageUrlMixin, AsciiSlugMixin, Page):
    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        # Use Django's request language (set by LocaleMiddleware from URL/cookie) rather
        # than get_language(), which Wagtail overrides to the page's own locale inside serve().
        lang = getattr(request, "LANGUAGE_CODE", None) or get_language()
        context["site_content"] = LocalizedSiteContent(SiteContent.load(), lang)
        context["cards"] = localized_cards(lang)
        from home.seo import organization

        site = self.get_site()
        context["structured_data"] = organization(request, context["site_content"], site.site_name if site else "")
        return context


class AboutPage(OwnLanguageUrlMixin, AsciiSlugMixin, Page):
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
