"""
Admin-writable, publicly-readable content API for the published models (NewsArticle,
KnowledgeArticle). News exposes full admin CRUD plus public reads, mirroring the competitions
API; knowledge exposes public reads plus admin create (one article per locale, each with its own
slug/URL) -- editing/moderation still happens through the on-site Django views. The DraftSubmission
community-submission workflow is web-only (news/knowledge views).
"""

from datetime import datetime

from django.db.models import Field
from django.utils.translation import gettext as _
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from api.schemas import LocalizedStr, localize_field
from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
from knowledge.models import KnowledgeArticle
from news.models import NewsArticle

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()

news_router = Router(tags=["news"])
knowledge_router = Router(tags=["knowledge"])


# -- Schemas ------------------------------------------------------------------


class NewsArticleOut(Schema):
    id: int
    title: LocalizedStr
    intro: LocalizedStr
    body: LocalizedStr
    slug: str
    published_at: datetime
    is_hidden: bool
    published_by_id: int | None

    @staticmethod
    def resolve_title(obj: NewsArticle) -> LocalizedStr:
        return localize_field(obj, "title")

    @staticmethod
    def resolve_intro(obj: NewsArticle) -> LocalizedStr:
        return localize_field(obj, "intro")

    @staticmethod
    def resolve_body(obj: NewsArticle) -> LocalizedStr:
        return localize_field(obj, "body")


class NewsArticleIn(Schema):
    title: LocalizedStr
    intro: LocalizedStr = LocalizedStr()
    body: LocalizedStr = LocalizedStr()
    is_hidden: bool = False


class NewsArticlePatchIn(Schema):
    title: LocalizedStr | None = None
    intro: LocalizedStr | None = None
    body: LocalizedStr | None = None
    is_hidden: bool | None = None


class KnowledgeArticleOut(Schema):
    id: int
    title: str
    slug: str
    locale: str
    category: str
    body: str  # already-sanitized HTML
    published_at: datetime
    is_hidden: bool
    published_by_id: int | None


class KnowledgeArticleIn(Schema):
    title: str
    locale: str = "ru"
    body: str = ""
    category: str = ""
    is_hidden: bool = False


# -- Helpers ------------------------------------------------------------------


def _require_admin(user) -> None:
    if not is_admin(user):
        raise HttpError(403, "Admin role is required")


def _validate_body_length(body: str | None) -> None:
    if body and len(body) > MAX_RICH_TEXT_LENGTH:
        raise HttpError(422, _("Body is too large (max %(limit)d characters).") % {"limit": MAX_RICH_TEXT_LENGTH})


def _validate_localized_length(value: LocalizedStr, field: str, message: str) -> None:
    # Limit each locale to the model column width, so an over-long value fails with a 422 rather
    # than a database DataError (500) inside NewsArticle.save(). `message` is an already-translated
    # %(limit)d format string supplied by the caller.
    field_obj = NewsArticle._meta.get_field(field)
    limit = field_obj.max_length if isinstance(field_obj, Field) else None
    if limit is None:
        return
    for raw in (value.ru, value.kk, value.en):
        if raw and len(raw) > limit:
            raise HttpError(422, message % {"limit": limit})


def _validate_news_title(title: LocalizedStr) -> None:
    # Require a non-whitespace title: a value like "   " is truthy but visually empty, and would
    # otherwise save a blank article that slugifies to the technical "article" fallback.
    if not any((value or "").strip() for value in (title.ru, title.kk, title.en)):
        raise HttpError(422, _("At least one title translation is required."))
    _validate_localized_length(title, "title", _("Title is too long (max %(limit)d characters)."))


def _validate_knowledge_payload(payload: KnowledgeArticleIn) -> None:
    if payload.locale not in {code for code, _label in KnowledgeArticle.LOCALE_CHOICES}:
        raise HttpError(422, _("Unknown locale."))
    if not (payload.title or "").strip():
        raise HttpError(422, _("A title is required."))
    # Bound title/category to their column widths so an over-long value fails with a 422
    # rather than a database DataError (500) inside KnowledgeArticle.save().
    for field, value, message in (
        ("title", payload.title, _("Title is too long (max %(limit)d characters).")),
        ("category", payload.category, _("Category is too long (max %(limit)d characters).")),
    ):
        field_obj = KnowledgeArticle._meta.get_field(field)
        limit = field_obj.max_length if isinstance(field_obj, Field) else None
        if limit is not None and value and len(value) > limit:
            raise HttpError(422, message % {"limit": limit})
    _validate_body_length(payload.body)


def _get_news_article_or_404(pk: int) -> NewsArticle:
    try:
        return NewsArticle.objects.get(pk=pk, is_deleted=False)
    except NewsArticle.DoesNotExist:
        raise HttpError(404, "Not found") from None


def _apply_news_localized(article: NewsArticle, field: str, value: LocalizedStr) -> None:
    for lang in ("ru", "kk", "en"):
        setattr(article, f"{field}_{lang}", getattr(value, lang))
    # Set the canonical column via __dict__: setattr(article, field, ...) goes through
    # modeltranslation's descriptor and, under a non-default active language, would write the value
    # into that language's column instead (corrupting an otherwise-empty translation). Matches
    # api/endpoints/competitions.py::_apply_localized.
    article.__dict__[field] = value.ru or value.kk or value.en


# -- News endpoints -----------------------------------------------------------


@news_router.get("/", response=list[NewsArticleOut], auth=optional_auth, summary="List news articles")
def list_news(request):
    user = request.auth
    qs = NewsArticle.objects.filter(is_deleted=False)
    if not is_admin(user):
        qs = qs.filter(is_hidden=False)
    return list(qs)


@news_router.get("/{pk}", response=NewsArticleOut, auth=optional_auth, summary="Get news article")
def get_news(request, pk: int):
    user = request.auth
    article = _get_news_article_or_404(pk)
    if article.is_hidden and not is_admin(user):
        raise HttpError(404, "Not found")
    return article


@news_router.post("/", response={201: NewsArticleOut}, auth=auth, summary="Create a news article (admin)")
def create_news_article(request, payload: NewsArticleIn):
    """Create a NewsArticle (the model rendered on /news/) from one multi-locale request.

    Body HTML is sanitized centrally in NewsArticle.save() (with images allowed), so the API and
    the on-site form store identical markup.
    """
    user = request.auth
    _require_admin(user)
    _validate_news_title(payload.title)
    _validate_localized_length(payload.intro, "intro", _("Intro is too long (max %(limit)d characters)."))
    for raw in (payload.body.ru, payload.body.kk, payload.body.en):
        _validate_body_length(raw)

    article = NewsArticle(published_by=user, is_hidden=payload.is_hidden)
    for field, value in (("title", payload.title), ("intro", payload.intro), ("body", payload.body)):
        _apply_news_localized(article, field, value)
    article.save()
    return Status(201, article)


@news_router.patch("/{pk}", response=NewsArticleOut, auth=auth, summary="Update a news article (admin)")
def update_news_article(request, pk: int, payload: NewsArticlePatchIn):
    user = request.auth
    _require_admin(user)
    article = _get_news_article_or_404(pk)

    data = payload.dict(exclude_unset=True)
    if payload.title is not None:
        _validate_news_title(payload.title)
    if payload.intro is not None:
        _validate_localized_length(payload.intro, "intro", _("Intro is too long (max %(limit)d characters)."))
    if payload.body is not None:
        for raw in (payload.body.ru, payload.body.kk, payload.body.en):
            _validate_body_length(raw)
    for field in ("title", "intro", "body"):
        if field in data and getattr(payload, field) is not None:
            _apply_news_localized(article, field, getattr(payload, field))
    if payload.is_hidden is not None:
        article.is_hidden = payload.is_hidden
    article.save()
    return article


@news_router.delete("/{pk}", response={204: None}, auth=auth, summary="Delete a news article (admin, soft)")
def delete_news_article(request, pk: int):
    user = request.auth
    _require_admin(user)
    article = _get_news_article_or_404(pk)
    article.is_deleted = True
    article.save(update_fields=["is_deleted"])
    return Status(204, None)


# -- Knowledge: public read serves the published KnowledgeArticle -------------


@knowledge_router.get("/", response=list[KnowledgeArticleOut], auth=optional_auth, summary="List knowledge articles")
def list_knowledge_articles(request):
    user = request.auth
    qs = KnowledgeArticle.objects.filter(is_deleted=False)
    if not is_admin(user):
        qs = qs.filter(is_hidden=False)
    return list(qs)


@knowledge_router.get(
    "/{article_id}", response=KnowledgeArticleOut, auth=optional_auth, summary="Get knowledge article"
)
def get_knowledge_article(request, article_id: int):
    user = request.auth
    try:
        article = KnowledgeArticle.objects.get(pk=article_id, is_deleted=False)
    except KnowledgeArticle.DoesNotExist:
        raise HttpError(404, "Not found") from None
    if article.is_hidden and not is_admin(user):
        raise HttpError(404, "Not found")
    return article


@knowledge_router.post(
    "/", response={201: KnowledgeArticleOut}, auth=auth, summary="Create a knowledge article (admin)"
)
def create_knowledge_article(request, payload: KnowledgeArticleIn):
    """Create a KnowledgeArticle (rendered under /knowledge/) for one locale.

    Each locale is its own article with its own slug/URL. Body HTML is sanitized centrally in
    KnowledgeArticle.save() (same allowlist as the on-site form), and the slug is generated there.
    """
    user = request.auth
    _require_admin(user)
    _validate_knowledge_payload(payload)

    article = KnowledgeArticle(
        title=payload.title.strip(),
        locale=payload.locale,
        body=payload.body,
        category=payload.category.strip(),
        is_hidden=payload.is_hidden,
        published_by=user,
    )
    article.save()
    return Status(201, article)
