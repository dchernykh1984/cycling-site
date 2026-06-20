from typing import ClassVar

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from taggit.managers import TaggableManager
from wagtail.admin.panels import FieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.fields import RichTextField
from wagtail.models import Page
from wagtail.search import index
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin
from cycling_site.sanitize import sanitize_rich_html

# Cap the stored size (characters) of an article body. Inline images are embedded as base64
# data URIs, so without a limit a body could bloat the DB / API payloads / requests without
# bound. Enforced on the untrusted write paths (organizer form, participant submission, API);
# mirrors calendar_app.MAX_DESCRIPTION_LENGTH.
MAX_BODY_LENGTH = 1_000_000


class KnowledgeArticle(index.Indexed, models.Model):
    """Frontend-managed knowledge article: a plain Django model with an HTML body edited
    on-site via Quill (mirrors calendar_app.Competition / news.NewsArticle).

    Single-language per article (the `locale` field), no per-locale translation columns:
    users write in one language; we may add the same article in another language as a
    separate row. Sanitized centrally in save(); searchable via index.Indexed.
    """

    LOCALE_CHOICES: ClassVar[list] = [("ru", _("Russian")), ("kk", _("Kazakh")), ("en", _("English"))]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    locale = models.CharField(max_length=10, choices=LOCALE_CHOICES, default="ru", db_index=True)
    body = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    tags = TaggableManager(blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)  # real last-edit time for the sitemap
    is_hidden = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    search_fields: ClassVar[list] = [
        index.SearchField("title"),
        index.SearchField("body"),
        index.FilterField("category"),
        index.FilterField("locale"),
        index.FilterField("is_hidden"),
        index.FilterField("is_deleted"),
    ]

    class Meta:
        ordering: ClassVar[list] = ["-published_at"]
        verbose_name = "Knowledge article"
        verbose_name_plural = "Knowledge articles"

    def __str__(self) -> str:
        return self.title or ""

    def save(self, *args, **kwargs) -> None:
        # Body is rendered with |safe, so sanitize on every write (single choke point for
        # the organizer form, participant submission approval and Django admin).
        if self.body:
            self.body = sanitize_rich_html(self.body, allow_img=True)
        if not self.slug:
            base = slugify(self.title or "", allow_unicode=False) or "article"
            candidate = base
            n = 1
            while KnowledgeArticle.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{n}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        from wagtail.models import Locale

        loc = Locale.objects.filter(language_code=self.locale).first()
        index_page = None
        if loc is not None:
            index_page = KnowledgeIndexPage.objects.live().filter(locale=loc).first()
        if index_page is None:
            index_page = KnowledgeIndexPage.objects.live().first()
        return f"{index_page.url}{self.slug}/" if index_page else f"/knowledge/{self.slug}/"


def _can_manage_knowledge(user) -> bool:
    from accounts.models import User

    admin_rank = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= admin_rank)


class KnowledgeIndexPage(RoutablePageMixin, AsciiSlugMixin, Page):
    intro = RichTextField(blank=True)

    content_panels: ClassVar[list] = [*Page.content_panels, FieldPanel("intro")]

    # Articles are now a plain KnowledgeArticle model, not child pages.
    subpage_types: ClassVar[list] = []

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request):
        from django.core.paginator import Paginator
        from django.urls import reverse

        from accounts.models import User

        context = super().get_context(request)
        can_manage = _can_manage_knowledge(request.user)
        articles = KnowledgeArticle.objects.filter(locale=self.locale.language_code, is_deleted=False)
        if not can_manage:
            articles = articles.filter(is_hidden=False)
        articles = articles.order_by("-published_at")
        paginator = Paginator(articles, 12)
        context["articles"] = paginator.get_page(request.GET.get("page", 1))

        can_add = False
        if request.user.is_authenticated:
            participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
            can_add = request.user.get_role_rank() >= participant_rank
        if can_manage:
            context["add_article_url"] = reverse("knowledge_add")
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
        return context

    @path("")
    def index_route(self, request):
        return self.render(request)

    @path("<slug:slug>/")
    def article_route(self, request, slug):
        from django.http import Http404
        from django.shortcuts import render
        from django.urls import reverse
        from django.utils.translation import get_language, gettext
        from django.utils.translation import override as translation_override

        can_manage = _can_manage_knowledge(request.user)
        article = KnowledgeArticle.objects.filter(slug=slug, is_deleted=False).first()
        if article is None or (article.is_hidden and not can_manage):
            raise Http404
        context = {"page": self, "article": article, "can_edit": can_manage}

        user_lang = (getattr(request, "LANGUAGE_CODE", None) or get_language() or "").split("-")[0]
        if user_lang and user_lang != article.locale:
            with translation_override(user_lang):
                context["locale_mismatch_message"] = gettext(
                    "This article isn't available in your selected language, so it's shown in its original language."
                )
                context["locale_mismatch_search_cta"] = gettext("Search for a similar article in your language")
            context["locale_mismatch"] = True
            context["search_url"] = reverse("search")
        return render(request, "knowledge/knowledge_article_detail.html", context)

    class Meta:
        verbose_name = "Knowledge index page"


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
        # reviewer is unused for the plain model (kept for signature parity with the news path).
        del reviewer
        # KnowledgeArticle.save() sanitizes the body and assigns a unique ASCII slug.
        KnowledgeArticle.objects.create(
            title=self.title,
            locale=self.locale,
            body=self.body,
            category=self.category,
            published_by=self.author,
            published_at=timezone.now(),
        )

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

        body_json = json.dumps([{"type": "text", "value": sanitize_rich_html(self.body)}])
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
