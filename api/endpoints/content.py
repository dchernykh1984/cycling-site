"""
Admin-writable, publicly-readable content API for the published models (NewsArticle,
KnowledgeArticle). News exposes full admin CRUD plus public reads, mirroring the competitions
API; knowledge exposes public reads, admin create (one article per locale, each with its own
slug/URL), and the participant/organizer draft-submission workflow (POST /knowledge/drafts/, with
admin authors auto-approved) -- article editing/hiding still happens through the on-site views.
"""

from datetime import datetime

from django.db.models import Field
from django.utils.translation import gettext as _
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, OptionalApiTokenAuth, is_admin
from api.schemas import LocalizedStr, localize_field
from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
from knowledge.models import DraftSubmission, KnowledgeArticle
from news.models import NewsArticle

auth = ApiTokenAuth()
optional_auth = OptionalApiTokenAuth()

news_router = Router(tags=["news"])
knowledge_router = Router(tags=["knowledge"])

_LOCALE_VALUES = ("ru", "kk", "en")


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


class KnowledgeArticlePatchIn(Schema):
    title: str | None = None
    locale: str | None = None
    body: str | None = None
    category: str | None = None
    is_hidden: bool | None = None


class DraftIn(Schema):
    title: str
    body: str
    locale: str
    category: str = ""


class DraftPatchIn(Schema):
    title: str | None = None
    body: str | None = None
    locale: str | None = None
    category: str | None = None


class DraftOut(Schema):
    id: int
    submission_type: str
    title: str
    body: str
    locale: str
    category: str
    status: str
    submitted_at: datetime
    author_id: int
    reviewer_note: str


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


def _validate_knowledge_patch(data: dict) -> None:
    if "locale" in data and data["locale"] not in {code for code, _label in KnowledgeArticle.LOCALE_CHOICES}:
        raise HttpError(422, _("Unknown locale."))
    if "title" in data and not (data["title"] or "").strip():
        raise HttpError(422, _("A title is required."))
    for field, message in (
        ("title", _("Title is too long (max %(limit)d characters).")),
        ("category", _("Category is too long (max %(limit)d characters).")),
    ):
        if data.get(field):
            field_obj = KnowledgeArticle._meta.get_field(field)
            limit = field_obj.max_length if isinstance(field_obj, Field) else None
            if limit is not None and len(data[field]) > limit:
                raise HttpError(422, message % {"limit": limit})
    if "body" in data:
        _validate_body_length(data["body"])


def _get_knowledge_article_or_404(article_id: int) -> KnowledgeArticle:
    try:
        return KnowledgeArticle.objects.get(pk=article_id, is_deleted=False)
    except KnowledgeArticle.DoesNotExist:
        raise HttpError(404, "Not found") from None


# -- Knowledge draft-submission helpers (participant/organizer authoring) ------


def _require_min_participant(user) -> None:
    if user.get_role_rank() < 1:
        raise HttpError(403, "Verified participant role or higher is required")


def _get_draft_or_404(pk: int, submission_type: str) -> DraftSubmission:
    try:
        return DraftSubmission.objects.get(pk=pk, submission_type=submission_type)
    except DraftSubmission.DoesNotExist:
        raise HttpError(404, "Draft not found") from None


def _require_owner_or_admin(user, draft: DraftSubmission) -> None:
    if draft.author_id != user.pk and not is_admin(user):
        raise HttpError(403, "Forbidden")


def _validate_locale(locale: str) -> None:
    if locale not in _LOCALE_VALUES:
        raise HttpError(422, f"locale must be one of: {', '.join(_LOCALE_VALUES)}")


def _create_draft(request, payload: DraftIn, submission_type: str) -> DraftSubmission:
    user = request.auth
    _require_min_participant(user)
    _validate_locale(payload.locale)
    _validate_body_length(payload.body)

    draft = DraftSubmission.objects.create(
        author=user,
        submission_type=submission_type,
        title=payload.title,
        body=payload.body,
        locale=payload.locale,
        category=payload.category,
    )

    # An admin/owner author needs no moderation, so publish immediately (mirrors the on-site
    # "add article" flow); a lower role's submission stays PENDING for a manager to approve.
    if is_admin(user):
        try:
            draft.approve(reviewer=user)
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc

    return draft


def _update_draft(request, pk: int, payload: DraftPatchIn, submission_type: str) -> DraftSubmission:
    user = request.auth
    draft = _get_draft_or_404(pk, submission_type)
    _require_owner_or_admin(user, draft)

    if draft.status != DraftSubmission.Status.PENDING:
        raise HttpError(409, "Only PENDING drafts can be edited")

    data = payload.dict(exclude_unset=True)
    if "locale" in data:
        _validate_locale(data["locale"])
    if "body" in data:
        _validate_body_length(data["body"])

    update_fields = []
    for field, value in data.items():
        setattr(draft, field, value)
        update_fields.append(field)
    if update_fields:
        draft.save(update_fields=update_fields)

    return draft


def _delete_draft(request, pk: int, submission_type: str) -> None:
    user = request.auth
    draft = _get_draft_or_404(pk, submission_type)
    _require_owner_or_admin(user, draft)

    if draft.status != DraftSubmission.Status.PENDING:
        raise HttpError(409, "Only PENDING drafts can be deleted")

    draft.delete()


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


# Draft submissions: authoring for participants/organizers. Registered before the
# "/{article_id}" article route (drafts are moderation data, never public reads).


@knowledge_router.get("/drafts/", response=list[DraftOut], auth=auth, summary="List own knowledge article drafts")
def list_knowledge_drafts(request, status: DraftSubmission.Status | None = None):
    # Drafts are moderation data, never public: require auth and show a non-admin only their own
    # submissions. Published content is read via the public KnowledgeArticle endpoints.
    user = request.auth
    qs = DraftSubmission.objects.filter(submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    if not is_admin(user):
        qs = qs.filter(author=user)
    if status is not None:
        qs = qs.filter(status=status)
    return list(qs)


@knowledge_router.get("/drafts/{draft_id}", response=DraftOut, auth=auth, summary="Get own knowledge article draft")
def get_knowledge_draft(request, draft_id: int):
    user = request.auth
    draft = _get_draft_or_404(draft_id, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    _require_owner_or_admin(user, draft)
    return draft


@knowledge_router.post("/drafts/", response={201: DraftOut}, auth=auth, summary="Create knowledge article draft")
def create_knowledge_draft(request, payload: DraftIn):
    """Submit a knowledge article for moderation.

    Any verified participant or higher may submit; an admin/owner author is auto-approved and the
    article is published immediately, matching the on-site authoring flow.
    """
    draft = _create_draft(request, payload, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    return Status(201, draft)


@knowledge_router.patch("/drafts/{draft_id}", response=DraftOut, auth=auth, summary="Update knowledge article draft")
def update_knowledge_draft(request, draft_id: int, payload: DraftPatchIn):
    return _update_draft(request, draft_id, payload, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)


@knowledge_router.delete(
    "/drafts/{draft_id}", response={204: None}, auth=auth, summary="Delete knowledge article draft"
)
def delete_knowledge_draft(request, draft_id: int):
    _delete_draft(request, draft_id, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    return Status(204, None)


@knowledge_router.get(
    "/{article_id}", response=KnowledgeArticleOut, auth=optional_auth, summary="Get knowledge article"
)
def get_knowledge_article(request, article_id: int):
    user = request.auth
    article = _get_knowledge_article_or_404(article_id)
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


@knowledge_router.patch(
    "/{article_id}", response=KnowledgeArticleOut, auth=auth, summary="Update a knowledge article (admin)"
)
def update_knowledge_article(request, article_id: int, payload: KnowledgeArticlePatchIn):
    """Patch a published KnowledgeArticle (only the given fields).

    The slug is not regenerated on a title change, so the article URL stays stable. Body HTML is
    re-sanitized in KnowledgeArticle.save().
    """
    user = request.auth
    _require_admin(user)
    article = _get_knowledge_article_or_404(article_id)
    data = payload.dict(exclude_unset=True)
    _validate_knowledge_patch(data)
    for field in ("title", "locale", "body", "category", "is_hidden"):
        if field in data:
            value = data[field]
            if field in ("title", "category") and value is not None:
                value = value.strip()
            setattr(article, field, value)
    article.save()
    return article
