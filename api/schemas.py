"""Shared schema types used across multiple API endpoints.

The bounded string types below exist because a limit that lives only in the database is enforced in
the worst possible place: an over-long value passes validation, reaches the INSERT, and comes back
as a 500 rather than a 422 naming the field. That is how a 294-character registration link -- a
Google form with a Facebook click-id glued on -- failed a nightly agent run twice against a
varchar(200) column, and it would have done the same to anyone using the site's own form.

The numbers are written out rather than read off the models, so they are plain in the generated
OpenAPI and mypy can see them. ``api.tests`` asserts each one still matches the column it stands
for, so widening a column cannot leave the API refusing what the database would now accept.
"""

from typing import Annotated, Any

from ninja import Schema
from pydantic import Field

# calendar_app.Competition.url_route and its four siblings (Django's URLField default).
MAX_URL_LENGTH = 200
# calendar_app.Competition.title, locations.Location.name, knowledge/news article titles.
MAX_TITLE_LENGTH = 255
# knowledge.KnowledgeArticle.category and DraftSubmission.category.
MAX_CATEGORY_LENGTH = 100

Url = Annotated[str, Field(max_length=MAX_URL_LENGTH)]
Title = Annotated[str, Field(max_length=MAX_TITLE_LENGTH)]
Category = Annotated[str, Field(max_length=MAX_CATEGORY_LENGTH)]


class LocalizedStr(Schema):
    """A string value with translations for all three supported locales."""

    ru: str = ""
    kk: str = ""
    en: str = ""


class LocalizedTitle(LocalizedStr):
    """A localized name or title, every locale bounded like the column behind it."""

    ru: Title = ""
    kk: Title = ""
    en: Title = ""


def localize_field(obj: Any, field: str) -> LocalizedStr:
    # Use __dict__ to bypass modeltranslation's language proxy and read the raw DB column value.
    raw = obj.__dict__.get(field) if hasattr(obj, "__dict__") else None
    fallback = raw if isinstance(raw, str) and raw else ""
    return LocalizedStr(
        ru=getattr(obj, f"{field}_ru", None) or fallback,
        kk=getattr(obj, f"{field}_kk", None) or fallback,
        en=getattr(obj, f"{field}_en", None) or fallback,
    )
