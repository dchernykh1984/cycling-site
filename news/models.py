from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone
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


class NewsPageTag(TaggedItemBase):
    content_object = ParentalKey(
        "NewsPage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class NewsIndexPage(Page):
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


class NewsPage(Page):
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
        if not request.user.is_staff:
            qs = qs.filter(is_approved=True)
        context["comments"] = qs

        can_comment = False
        if request.user.is_authenticated:
            participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
            can_comment = request.user.get_role_rank() >= participant_rank
        context["can_comment"] = can_comment
        if can_comment:
            context["comment_form"] = AddCommentForm()
        context["user_can_delete_comment"] = request.user.is_staff
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


@register_setting
class NewsSettings(BaseGenericSetting):
    auto_approve_comments = models.BooleanField(
        default=True,
        help_text="Automatically approve new comments without admin review.",
    )

    panels: ClassVar[list] = [FieldPanel("auto_approve_comments")]

    class Meta:
        verbose_name = "News settings"
