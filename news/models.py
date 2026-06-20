from typing import ClassVar

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import RichTextBlock
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page
from wagtail.search import index
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin
from cycling_site.sanitize import sanitize_rich_html


class NewsPageTag(TaggedItemBase):
    content_object = ParentalKey(
        "NewsPage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class NewsIndexPage(AsciiSlugMixin, Page):
    intro = RichTextField(blank=True)

    content_panels: ClassVar[list] = [*Page.content_panels, FieldPanel("intro")]

    parent_page_types: ClassVar[list] = ["home.HomePage"]
    subpage_types: ClassVar[list] = ["news.NewsPage"]

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request):
        from django.core.paginator import Paginator

        context = super().get_context(request)
        news_items = NewsPage.objects.live().child_of(self).order_by("-published_at", "-first_published_at")
        paginator = Paginator(news_items, 12)
        context["news_items"] = paginator.get_page(request.GET.get("page", 1))
        return context

    class Meta:
        verbose_name = "News index page"


class NewsPage(AsciiSlugMixin, Page):
    intro = models.CharField(max_length=500, blank=True)
    body = StreamField(
        [
            ("text", RichTextBlock()),
            ("image", ImageChooserBlock()),
            ("embed", EmbedBlock()),
        ],
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
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_at = models.DateTimeField(default=timezone.now)
    tags = ClusterTaggableManager(through=NewsPageTag, blank=True)
    location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    content_panels: ClassVar[list] = [
        *Page.content_panels,
        FieldPanel("intro"),
        FieldPanel("hero_image"),
        FieldPanel("published_by"),
        FieldPanel("published_at"),
        FieldPanel("tags"),
        FieldPanel("location"),
        FieldPanel("body"),
    ]

    parent_page_types: ClassVar[list] = ["news.NewsIndexPage"]
    subpage_types: ClassVar[list] = []

    search_fields: ClassVar[list] = [
        *Page.search_fields,
        index.SearchField("intro"),
        index.SearchField("body"),
    ]

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request):
        from accounts.models import User
        from news.forms import AddCommentForm

        context = super().get_context(request)
        qs = Comment.objects.filter(page=self).select_related("author").order_by("created_at")
        admin_rank = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
        is_manager = request.user.is_authenticated and (
            request.user.is_superuser or request.user.get_role_rank() >= admin_rank
        )
        if not is_manager:
            qs = qs.filter(is_approved=True)
        context["comments"] = qs

        can_comment = False
        if request.user.is_authenticated:
            participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
            can_comment = request.user.get_role_rank() >= participant_rank
        context["can_comment"] = can_comment
        if can_comment:
            context["comment_form"] = AddCommentForm()
        context["user_can_delete_comment"] = is_manager
        return context

    class Meta:
        verbose_name = "News article"


class Comment(models.Model):
    page = models.ForeignKey(NewsPage, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="news_comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar[list] = ["created_at"]
        verbose_name = "Comment"

    def __str__(self) -> str:
        return f"Comment by {self.author} on {self.page}"


class NewsArticle(index.Indexed, models.Model):  # type: ignore[django-manager-missing]
    """Frontend-managed news article with per-locale title/intro/body fields.

    Modeltranslation adds title_ru/kk/en, intro_ru/kk/en, body_ru/kk/en.
    The virtual `title`, `intro`, `body` attributes resolve to the active locale.
    """

    title = models.CharField(max_length=255)
    intro = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)
    hero_image = models.ImageField(upload_to="news/hero/", null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="news_articles",
    )
    published_at = models.DateTimeField(default=timezone.now)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    is_hidden = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    # Per-locale rich-text body columns, sanitized on every write. Accessed via __dict__ in
    # save() so we never go through modeltranslation's canonical `body` descriptor (whose
    # getter returns another language's fallback for an empty translation).
    _BODY_FIELDS: ClassVar[tuple] = ("body", "body_ru", "body_kk", "body_en")

    search_fields: ClassVar[list] = [
        index.SearchField("title_ru"),
        index.SearchField("title_kk"),
        index.SearchField("title_en"),
        index.SearchField("body_ru"),
        index.SearchField("body_kk"),
        index.SearchField("body_en"),
        index.FilterField("is_hidden"),
        index.FilterField("is_deleted"),
    ]

    class Meta:
        ordering: ClassVar[list] = ["-published_at"]
        verbose_name = "News article"
        verbose_name_plural = "News articles"

    def __str__(self) -> str:
        return self.title or ""

    def save(self, *args, **kwargs) -> None:
        # Bodies are rendered with |safe, so sanitize on every write (single choke point for
        # the manager form and Django admin). See _BODY_FIELDS for the __dict__ rationale.
        update_fields = kwargs.get("update_fields")
        if update_fields is None or any(f in update_fields for f in self._BODY_FIELDS):
            for field in self._BODY_FIELDS:
                value = self.__dict__.get(field)
                if value:
                    self.__dict__[field] = sanitize_rich_html(value, allow_img=True)
        if not self.slug:
            # Prefer Russian title for the slug (stable across locale switches).
            base = slugify(getattr(self, "title_ru", None) or self.title or "article")
            if not base:
                base = "article"
            candidate = base
            n = 1
            while NewsArticle.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{n}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("news_article_detail", kwargs={"pk": self.pk})


@register_setting
class NewsSettings(BaseGenericSetting):
    auto_approve_comments = models.BooleanField(
        default=True,
        help_text="Automatically approve new comments without admin review.",
    )

    panels: ClassVar[list] = [FieldPanel("auto_approve_comments")]

    class Meta:
        verbose_name = "News settings"
