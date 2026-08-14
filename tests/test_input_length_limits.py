"""Every way into the database has to measure a value before the column does.

A limit that lives only in the schema is enforced in the worst possible place: an over-long value
passes validation, reaches the INSERT, and comes back as a DataError -- a 500 for the caller and an
error email for the maintainer, naming neither the field nor the limit. That is how a 294-character
registration link (a Google form with a Facebook click-id glued on) failed two nightly agent runs.

Fixing the places that were wrong is not what stops it happening again; this is. Each input surface
is listed here against the model it writes to, and a field that maps to a bounded column must be
bounded itself -- by the form field, by the request schema, or by a named check in the handler.

When this fails, the fix is one of:
  * give the form field ``max_length=<Model>._meta.get_field(...).max_length``;
  * annotate the schema field with one of the bounded aliases in ``api.schemas``;
  * or record the field in CHECKED_ELSEWHERE, naming what checks it instead.

A new form or request schema has to be listed too: the last test fails until it is, so a surface
cannot be added without someone deciding which model it writes to.
"""

import importlib
import inspect

from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Field
from django.test import SimpleTestCase
from ninja import Schema

from calendar_app.models import Competition, CompetitionComment
from knowledge.models import DraftSubmission, KnowledgeArticle, KnowledgeArticleComment
from locations.models import Location
from news.models import NewsArticle, NewsArticleComment
from registrations.models import CompetitionRegistration, RegistrationCategory, Team

FORM_MODULES = (
    "accounts.views",
    "calendar_app.forms",
    "home.forms",
    "knowledge.forms",
    "locations.forms",
    "news.forms",
    "registrations.forms",
)

# Which model (or models) each form writes into. A form may feed more than one -- the registration
# settings carry the competition's own flags and the names of its categories -- and every one of
# them is searched for the column behind a field. ``None`` means the form writes nothing a column
# has to hold: a filter, a search, a confirmation.
FORM_TARGETS = {
    "accounts.views.ContactOwnersForm": None,
    "accounts.views.ProfileEditForm": None,
    "calendar_app.forms.AddCompetitionCommentForm": CompetitionComment,
    "calendar_app.forms.CompetitionFilterForm": None,
    "calendar_app.forms.RegistrationSettingsForm": (Competition, RegistrationCategory),
    "calendar_app.forms.RejectCompetitionForm": Competition,
    "calendar_app.forms.ReportCompetitionForm": None,
    "calendar_app.forms.SubmitCompetitionForm": Competition,
    "home.forms.SiteContentForm": None,
    "knowledge.forms.AddKnowledgeArticleCommentForm": KnowledgeArticleComment,
    "knowledge.forms.DraftSubmissionForm": DraftSubmission,
    "knowledge.forms.KnowledgeArticleForm": KnowledgeArticle,
    "locations.forms.LocationForm": Location,
    "news.forms.AddCommentForm": None,
    "news.forms.AddNewsArticleCommentForm": NewsArticleComment,
    "news.forms.NewsArticleForm": NewsArticle,
    "news.forms.SubmitNewsForm": NewsArticle,
    "registrations.forms.EditRegistrationForm": (CompetitionRegistration, Team),
    "registrations.forms.RegistrationForm": (CompetitionRegistration, Team),
    "registrations.forms.RejectRegistrationForm": None,
}

# The same for request schemas -- the ones the routers actually accept a body into. A response
# schema needs no bound: it serializes rows the database has already accepted.
SCHEMA_TARGETS = {
    "api.endpoints.competitions.CompetitionIn": Competition,
    "api.endpoints.competitions.CompetitionPatchIn": Competition,
    "api.endpoints.content.DraftIn": DraftSubmission,
    "api.endpoints.content.DraftPatchIn": DraftSubmission,
    "api.endpoints.content.KnowledgeArticleIn": KnowledgeArticle,
    "api.endpoints.content.KnowledgeArticlePatchIn": KnowledgeArticle,
    "api.endpoints.content.NewsArticleIn": NewsArticle,
    "api.endpoints.content.NewsArticlePatchIn": NewsArticle,
    "api.endpoints.locations.LocationIn": Location,
    "api.endpoints.locations.LocationPatchIn": Location,
    # Timing and start-list payloads are device streams, not rows of these models: they carry a
    # competition token and a list of lines, parsed and validated by their own endpoints.
    "api.endpoints.live_stats.LiveStatsIn": None,
    "api.endpoints.start_list.StartListIn": None,
    "api.endpoints.timings.RemoteTimingIn": None,
    "api.endpoints.timings._TimingIn": None,
}

# A bounded column whose input is measured somewhere this test cannot see, with what does it.
CHECKED_ELSEWHERE = {
    ("api.endpoints.content.KnowledgeArticleIn", "title"): "_validate_knowledge_payload, localized 422",
    ("api.endpoints.content.KnowledgeArticleIn", "category"): "_validate_knowledge_payload, localized 422",
    ("api.endpoints.content.KnowledgeArticleIn", "locale"): "_validate_locale, against the choices",
    ("api.endpoints.content.KnowledgeArticlePatchIn", "title"): "_validate_knowledge_patch, localized 422",
    ("api.endpoints.content.KnowledgeArticlePatchIn", "category"): "_validate_knowledge_patch, localized 422",
    ("api.endpoints.content.KnowledgeArticlePatchIn", "locale"): "_validate_locale, against the choices",
    ("api.endpoints.content.DraftIn", "title"): "_validate_draft_lengths, localized 422",
    ("api.endpoints.content.DraftIn", "category"): "_validate_draft_lengths, localized 422",
    ("api.endpoints.content.DraftIn", "locale"): "_validate_locale, against the choices",
    ("api.endpoints.content.DraftPatchIn", "title"): "_validate_draft_lengths, localized 422",
    ("api.endpoints.content.DraftPatchIn", "category"): "_validate_draft_lengths, localized 422",
    ("api.endpoints.content.DraftPatchIn", "locale"): "_validate_locale, against the choices",
    ("api.endpoints.content.NewsArticleIn", "title"): "_validate_news_title, localized 422",
    ("api.endpoints.content.NewsArticleIn", "intro"): "_validate_localized_length, localized 422",
    ("api.endpoints.content.NewsArticlePatchIn", "title"): "_validate_news_title, localized 422",
    ("api.endpoints.content.NewsArticlePatchIn", "intro"): "_validate_localized_length, localized 422",
    ("calendar_app.forms.RegistrationSettingsForm", "categories_json"): "clean_categories_json, per category name",
}


def _forms():
    for module in FORM_MODULES:
        mod = importlib.import_module(module)
        for name, obj in vars(mod).items():
            if inspect.isclass(obj) and issubclass(obj, forms.BaseForm) and obj.__module__ == module:
                yield f"{module}.{name}", obj


def _request_schemas():
    """Every schema the API really accepts as a request body, read off the routers themselves.

    Not off a name: a schema called ``CompetitionPayload`` would be just as much an entrance, and a
    guard that can be stepped around by naming something differently is not a guard.
    """
    from api.router import api

    seen = {}
    for _prefix, router in api._routers:
        for _path, path_view in router.path_operations.items():
            for operation in path_view.operations:
                for param in inspect.signature(operation.view_func).parameters.values():
                    annotation = param.annotation
                    for candidate in [annotation, *(getattr(annotation, "__args__", ()) or ())]:
                        if inspect.isclass(candidate) and issubclass(candidate, Schema):
                            seen[f"{candidate.__module__}.{candidate.__name__}"] = candidate
    yield from sorted(seen.items())


def _column_limit(target, name: str) -> int | None:
    """What the column of that name holds, or None when no target model has such a bounded column.

    ``target`` is one model or several. ``name`` may carry a locale suffix: a form posts title_ru
    where the column is title. The narrowest limit wins, so a name shared by two models is held to
    whichever of them would refuse it first.
    """
    models = target if isinstance(target, tuple) else (target,)
    limits = []
    for model in models:
        for candidate in (name, name.rsplit("_", 1)[0]):
            try:
                field = model._meta.get_field(candidate)
            except FieldDoesNotExist:  # a form field with no column behind it is simply free
                continue
            if isinstance(field, Field) and field.max_length:
                limits.append(field.max_length)
    return min(limits) if limits else None


def _carries_a_maximum(constraint) -> bool:
    """Whether a pydantic constraint object bounds a length, at any depth.

    ``Annotated[str, Field(max_length=200)]`` leaves a bare ``MaxLen`` behind on a required field
    but wraps it in a ``FieldInfo`` once the field becomes optional, so the constraint has to be
    looked for rather than read off the top -- which is how the PATCH schema was left unguarded
    while the POST one looked fine.
    """
    if getattr(constraint, "max_length", None):
        return True
    return any(_carries_a_maximum(nested) for nested in getattr(constraint, "metadata", ()) or ())


def _carries_text(annotation) -> bool:
    """Whether a field can hold text -- directly, or inside a nested schema such as LocalizedStr.

    Looking for "str" in the printed annotation is not enough: ``LocalizedStr`` prints without it,
    which is exactly how a location name went unchecked while every plain string was covered.
    """
    for candidate in [annotation, *(getattr(annotation, "__args__", ()) or ())]:
        origin = getattr(candidate, "__origin__", candidate)
        if origin is str:
            return True
        if inspect.isclass(candidate) and issubclass(candidate, Schema):
            return any(_carries_text(sub.annotation) for sub in candidate.model_fields.values())
    return False


def _schema_field_is_bounded(info) -> bool:
    """Whether a pydantic field carries a maximum length, directly or through a nested schema."""
    if any(_carries_a_maximum(meta) for meta in info.metadata):
        return True
    for candidate in [info.annotation, *(getattr(info.annotation, "__args__", ()) or ())]:
        if any(_carries_a_maximum(meta) for meta in getattr(candidate, "__metadata__", ()) or ()):
            return True
        if inspect.isclass(candidate) and issubclass(candidate, Schema):
            nested = [sub for sub in candidate.model_fields.values() if _carries_text(sub.annotation)]
            if nested and all(_schema_field_is_bounded(sub) for sub in nested):
                return True
    return False


class FormLengthLimitTests(SimpleTestCase):
    """No form may take a text value longer than the column it is going to be written to."""

    def test_every_text_field_is_bounded_or_checked_elsewhere(self):
        unbounded = []
        for label, form_class in _forms():
            target = FORM_TARGETS.get(label)
            if target is None:
                continue
            try:
                instance = form_class()
            except TypeError:  # a form that needs constructor arguments is covered by its own tests
                continue
            for name, field in instance.fields.items():
                if not isinstance(field, forms.CharField) or isinstance(field, forms.ChoiceField):
                    continue
                if field.max_length or (label, name) in CHECKED_ELSEWHERE:
                    continue
                limit = _column_limit(target, name)
                if limit:
                    unbounded.append(f"{label}.{name} -> the column holds {limit}")
        self.assertEqual(
            unbounded, [], "these form fields accept more than the column will:\n  " + "\n  ".join(unbounded)
        )


class SchemaLengthLimitTests(SimpleTestCase):
    """The same for the API: a request field over a bounded column must be bounded too."""

    def test_every_request_string_is_bounded_or_checked_elsewhere(self):
        unbounded = []
        for label, schema in _request_schemas():
            target = SCHEMA_TARGETS.get(label)
            if target is None:
                continue
            for name, info in schema.model_fields.items():
                if not _carries_text(info.annotation) or (label, name) in CHECKED_ELSEWHERE:
                    continue
                if _schema_field_is_bounded(info):
                    continue
                limit = _column_limit(target, name)
                if limit:
                    unbounded.append(f"{label}.{name} -> the column holds {limit}")
        self.assertEqual(
            unbounded, [], "these request fields accept more than the column will:\n  " + "\n  ".join(unbounded)
        )


class SurfaceRegistryTests(SimpleTestCase):
    """The lists above have to stay complete and honest, or they become where gaps hide."""

    def test_every_form_is_accounted_for(self):
        missing = sorted(label for label, _cls in _forms() if label not in FORM_TARGETS)
        self.assertEqual(missing, [], f"add these to FORM_TARGETS (model, or None if it writes no column): {missing}")

    def test_every_request_schema_is_accounted_for(self):
        missing = sorted(label for label, _cls in _request_schemas() if label not in SCHEMA_TARGETS)
        self.assertEqual(missing, [], f"add these to SCHEMA_TARGETS: {missing}")

    def test_no_stale_entries(self):
        forms_seen = {label for label, _cls in _forms()}
        schemas_seen = {label for label, _cls in _request_schemas()}
        known = forms_seen | schemas_seen
        stale = sorted(label for label in {*FORM_TARGETS, *SCHEMA_TARGETS} if label not in known)
        self.assertEqual(stale, [], f"these surfaces no longer exist: {stale}")

    def test_no_stale_exemptions(self):
        forms_seen = {label for label, _cls in _forms()}
        schemas_seen = {label for label, _cls in _request_schemas()}
        stale = sorted(
            f"{label}.{field}" for label, field in CHECKED_ELSEWHERE if label not in forms_seen | schemas_seen
        )
        self.assertEqual(stale, [], f"exemptions for surfaces that no longer exist: {stale}")
