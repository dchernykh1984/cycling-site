from typing import ClassVar

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import CharBlock, ChoiceBlock, RichTextBlock, StructBlock, TextBlock, URLBlock
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page
from wagtail.search import index
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin


class CodeBlock(StructBlock):
    language = CharBlock(required=False, help_text="e.g. python, javascript, bash")
    code = TextBlock()

    class Meta:
        template = "knowledge/blocks/code_block.html"
        icon = "code"
        label = "Code block"


class ExternalLinkBlock(StructBlock):
    title = CharBlock()
    url = URLBlock()
    platform = ChoiceBlock(
        choices=[
            ("komoot", "Komoot"),
            ("strava", "Strava"),
            ("ridewithgps", "RideWithGPS"),
            ("other", "Other"),
        ],
        required=False,
        default="other",
    )

    class Meta:
        icon = "link"
        label = "External link"


class KnowledgeArticlePageTag(TaggedItemBase):
    content_object = ParentalKey(
        "KnowledgeArticlePage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class KnowledgeIndexPage(AsciiSlugMixin, Page):
    intro = RichTextField(blank=True)

    content_panels: ClassVar[list] = [*Page.content_panels, FieldPanel("intro")]

    subpage_types: ClassVar[list] = [
        "knowledge.KnowledgeArticlePage",
        "knowledge.LocationArticlePage",
    ]

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request):
        from django.core.paginator import Paginator
        from django.urls import reverse

        from accounts.models import User

        context = super().get_context(request)
        admin_rank = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
        can_manage = request.user.is_authenticated and (
            request.user.is_superuser or request.user.get_role_rank() >= admin_rank
        )
        articles = KnowledgeArticlePage.objects.live().child_of(self).filter(is_deleted=False)
        if not can_manage:
            articles = articles.filter(is_hidden=False)
        articles = articles.order_by("-first_published_at")
        paginator = Paginator(articles, 12)
        context["articles"] = paginator.get_page(request.GET.get("page", 1))

        can_add = False
        add_article_url = None
        if request.user.is_authenticated:
            participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
            can_add = request.user.get_role_rank() >= participant_rank
        if can_manage:
            add_article_url = reverse("knowledge_add")
            context["pending_submissions"] = (
                DraftSubmission.objects.filter(
                    status=DraftSubmission.Status.PENDING,
                    submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
                )
                .select_related("author")
                .order_by("submitted_at")
            )
        context["can_add"] = can_add
        context["can_manage"] = can_manage
        context["add_article_url"] = add_article_url
        return context

    class Meta:
        verbose_name = "Knowledge index page"


class KnowledgeArticlePage(AsciiSlugMixin, Page):
    body = StreamField(
        [
            ("text", RichTextBlock()),
            ("image", ImageChooserBlock()),
            ("embed", EmbedBlock()),
            ("code", CodeBlock()),
        ],
        blank=True,
        use_json_field=True,
    )
    category = models.CharField(max_length=100, blank=True)
    tags = ClusterTaggableManager(through=KnowledgeArticlePageTag, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    is_hidden = models.BooleanField(default=False, db_index=True)

    content_panels: ClassVar[list] = [
        *Page.content_panels,
        FieldPanel("category"),
        FieldPanel("tags"),
        FieldPanel("published_by"),
        FieldPanel("published_at"),
        FieldPanel("body"),
    ]

    parent_page_types: ClassVar[list] = ["knowledge.KnowledgeIndexPage"]
    subpage_types: ClassVar[list] = []

    search_fields: ClassVar[list] = [
        *Page.search_fields,
        index.SearchField("body"),
        index.FilterField("category"),
    ]

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def serve(self, request, *args, **kwargs):
        from django.http import Http404

        from accounts.models import User as _User

        can_manage = request.user.is_authenticated and (
            request.user.is_superuser or request.user.get_role_rank() >= _User.ROLE_HIERARCHY.index(_User.Role.ADMIN)
        )
        if self.is_deleted or (self.is_hidden and not can_manage):
            raise Http404
        response = super().serve(request, *args, **kwargs)
        if hasattr(response, "context_data"):
            response.context_data["can_edit"] = can_manage
        return response

    def get_context(self, request, *args, **kwargs):
        from accounts.models import User as _User

        context = super().get_context(request, *args, **kwargs)
        can_manage = request.user.is_authenticated and (
            request.user.is_superuser or request.user.get_role_rank() >= _User.ROLE_HIERARCHY.index(_User.Role.ADMIN)
        )
        context["can_edit"] = can_manage
        return context

    class Meta:
        verbose_name = "Knowledge article"


class LocationArticlePage(KnowledgeArticlePage):
    gpx_file = models.FileField(upload_to="knowledge/gpx/", blank=True)
    photo_gallery = StreamField(
        [("image", ImageChooserBlock())],
        blank=True,
        use_json_field=True,
    )
    external_links = StreamField(
        [("link", ExternalLinkBlock())],
        blank=True,
        use_json_field=True,
    )

    content_panels: ClassVar[list] = [
        *KnowledgeArticlePage.content_panels,
        FieldPanel("gpx_file"),
        FieldPanel("photo_gallery"),
        FieldPanel("external_links"),
    ]

    parent_page_types: ClassVar[list] = ["knowledge.KnowledgeIndexPage"]
    subpage_types: ClassVar[list] = []

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request):
        context = super().get_context(request)
        try:
            loc = self.location
            context["linked_location"] = loc
            if loc.lat is not None and loc.lng is not None:
                context["linked_location_lat"] = f"{float(loc.lat):.6f}"
                context["linked_location_lng"] = f"{float(loc.lng):.6f}"
        except Exception:
            context["linked_location"] = None
        return context

    class Meta:
        verbose_name = "Location article"


class DraftSubmission(models.Model):
    class SubmissionType(models.TextChoices):
        NEWS = "news", "News"
        KNOWLEDGE_ARTICLE = "knowledge_article", "Knowledge article"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="draft_submissions",
    )
    LOCALE_CHOICES: ClassVar[list] = [("ru", _("Russian")), ("kk", _("Kazakh")), ("en", _("English"))]

    submission_type = models.CharField(max_length=30, choices=SubmissionType.choices)
    locale = models.CharField(max_length=10, choices=LOCALE_CHOICES, verbose_name=_("Locale"))
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    body = models.TextField(verbose_name=_("Body"))
    category = models.CharField(max_length=100, blank=True, verbose_name=_("Category"))
    submitted_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_submissions",
    )
    reviewer_note = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list] = ["-submitted_at"]
        verbose_name = "Draft submission"

    def __str__(self) -> str:
        return f"{self.get_submission_type_display()} - {self.title}"

    def approve(self, reviewer) -> None:
        with transaction.atomic():
            locked = DraftSubmission.objects.select_for_update().get(pk=self.pk)
            if locked.status != DraftSubmission.Status.PENDING:
                raise ValueError(f"Cannot approve: submission is already '{locked.get_status_display()}'.")

            if self.submission_type == DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE:
                self._create_knowledge_article(reviewer)
            elif self.submission_type == DraftSubmission.SubmissionType.NEWS:
                self._create_news_page(reviewer)
            else:
                raise ValueError(f"Unknown submission type: '{self.submission_type}'.")

            self.status = DraftSubmission.Status.APPROVED
            self.reviewed_by = reviewer
            self.save(update_fields=["status", "reviewed_by"])

    def _create_knowledge_article(self, reviewer) -> None:
        import json

        from django.utils.text import slugify
        from wagtail.models import Locale

        try:
            locale = Locale.objects.get(language_code=self.locale)
        except Locale.DoesNotExist:
            raise ValueError(f"Locale '{self.locale}' is not configured in this Wagtail instance.") from None

        index = KnowledgeIndexPage.objects.live().filter(locale=locale).first()
        if index is None:
            raise ValueError(
                f"No live KnowledgeIndexPage found for locale '{self.locale}'. Create one in the Wagtail admin first."
            )

        base_slug = slugify(self.title) or "article"
        slug = base_slug
        counter = 1
        while KnowledgeArticlePage.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        body_json = json.dumps([{"type": "text", "value": f"<p>{escape(self.body)}</p>"}])
        article = KnowledgeArticlePage(
            title=self.title,
            slug=slug,
            body=body_json,
            category=self.category,
            published_by=self.author,
            published_at=timezone.now(),
            locale=locale,
        )
        index.add_child(instance=article)
        article.save_revision(user=reviewer).publish()

    def _create_news_page(self, reviewer) -> None:
        import json

        from django.utils.text import slugify
        from wagtail.models import Locale

        from news.models import NewsIndexPage, NewsPage

        try:
            locale = Locale.objects.get(language_code=self.locale)
        except Locale.DoesNotExist:
            raise ValueError(f"Locale '{self.locale}' is not configured in this Wagtail instance.") from None

        news_index = NewsIndexPage.objects.live().filter(locale=locale).first()
        if news_index is None:
            raise ValueError(
                f"No live NewsIndexPage found for locale '{self.locale}'. Create one in the Wagtail admin first."
            )

        base_slug = slugify(self.title) or "news"
        slug = base_slug
        counter = 1
        while NewsPage.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        body_json = json.dumps([{"type": "text", "value": f"<p>{escape(self.body)}</p>"}])
        news_page = NewsPage(
            title=self.title,
            slug=slug,
            body=body_json,
            published_by=self.author,
            published_at=timezone.now(),
            locale=locale,
        )
        news_index.add_child(instance=news_page)
        news_page.save_revision(user=reviewer).publish()

    def reject(self, reviewer, note: str = "") -> None:
        with transaction.atomic():
            locked = DraftSubmission.objects.select_for_update().get(pk=self.pk)
            if locked.status != DraftSubmission.Status.PENDING:
                raise ValueError(f"Cannot reject: submission is already '{locked.get_status_display()}'.")
            self.status = DraftSubmission.Status.REJECTED
            self.reviewed_by = reviewer
            self.reviewer_note = note
            self.save(update_fields=["status", "reviewed_by", "reviewer_note"])
