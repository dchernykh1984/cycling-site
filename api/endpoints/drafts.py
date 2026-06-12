"""
Shared endpoint logic for DraftSubmission-backed resources (news and knowledge articles).
Both submission types use the same model; they differ only in submission_type value.
"""

from datetime import datetime

from ninja import Router, Schema
from ninja.errors import HttpError

from api.auth import ApiTokenAuth, is_admin
from knowledge.models import DraftSubmission

auth = ApiTokenAuth()

news_router = Router(tags=["news"])
knowledge_router = Router(tags=["knowledge"])

_LOCALE_VALUES = ("ru", "kk", "en")


# -- Schemas ------------------------------------------------------------------


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

    draft = DraftSubmission.objects.create(
        author=user,
        submission_type=submission_type,
        title=payload.title,
        body=payload.body,
        locale=payload.locale,
        category=payload.category,
    )

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


# -- News endpoints -----------------------------------------------------------


@news_router.get("/", response=list[DraftOut], auth=auth, summary="List news drafts")
def list_news_drafts(request, status: DraftSubmission.Status | None = DraftSubmission.Status.APPROVED):
    user = request.auth
    qs = DraftSubmission.objects.filter(submission_type=DraftSubmission.SubmissionType.NEWS)
    if not is_admin(user):
        qs = qs.filter(author=user)
    if status:
        qs = qs.filter(status=status)
    return list(qs)


@news_router.get("/{draft_id}", response=DraftOut, auth=auth, summary="Get news draft")
def get_news_draft(request, draft_id: int):
    user = request.auth
    draft = _get_draft_or_404(draft_id, DraftSubmission.SubmissionType.NEWS)
    _require_owner_or_admin(user, draft)
    return draft


@news_router.post("/", response={201: DraftOut}, auth=auth, summary="Create news draft")
def create_news_draft(request, payload: DraftIn):
    draft = _create_draft(request, payload, DraftSubmission.SubmissionType.NEWS)
    return 201, draft


@news_router.patch("/{draft_id}", response=DraftOut, auth=auth, summary="Update news draft")
def update_news_draft(request, draft_id: int, payload: DraftPatchIn):
    return _update_draft(request, draft_id, payload, DraftSubmission.SubmissionType.NEWS)


@news_router.delete("/{draft_id}", response={204: None}, auth=auth, summary="Delete news draft")
def delete_news_draft(request, draft_id: int):
    _delete_draft(request, draft_id, DraftSubmission.SubmissionType.NEWS)
    return 204, None


# -- Knowledge article endpoints ----------------------------------------------


@knowledge_router.get("/", response=list[DraftOut], auth=auth, summary="List knowledge article drafts")
def list_knowledge_drafts(request, status: DraftSubmission.Status | None = DraftSubmission.Status.APPROVED):
    user = request.auth
    qs = DraftSubmission.objects.filter(submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    if not is_admin(user):
        qs = qs.filter(author=user)
    if status:
        qs = qs.filter(status=status)
    return list(qs)


@knowledge_router.get("/{draft_id}", response=DraftOut, auth=auth, summary="Get knowledge article draft")
def get_knowledge_draft(request, draft_id: int):
    user = request.auth
    draft = _get_draft_or_404(draft_id, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    _require_owner_or_admin(user, draft)
    return draft


@knowledge_router.post("/", response={201: DraftOut}, auth=auth, summary="Create knowledge article draft")
def create_knowledge_draft(request, payload: DraftIn):
    draft = _create_draft(request, payload, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    return 201, draft


@knowledge_router.patch("/{draft_id}", response=DraftOut, auth=auth, summary="Update knowledge article draft")
def update_knowledge_draft(request, draft_id: int, payload: DraftPatchIn):
    return _update_draft(request, draft_id, payload, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)


@knowledge_router.delete("/{draft_id}", response={204: None}, auth=auth, summary="Delete knowledge article draft")
def delete_knowledge_draft(request, draft_id: int):
    _delete_draft(request, draft_id, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
    return 204, None
