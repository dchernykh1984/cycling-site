"""Shared schema types used across multiple API endpoints."""

from typing import Any

from ninja import Schema


class LocalizedStr(Schema):
    """A string value with translations for all three supported locales."""

    ru: str = ""
    kk: str = ""
    en: str = ""


def localize_field(obj: Any, field: str) -> LocalizedStr:
    # Use __dict__ to bypass modeltranslation's language proxy and read the raw DB column value.
    raw = obj.__dict__.get(field) if hasattr(obj, "__dict__") else None
    fallback = raw if isinstance(raw, str) and raw else ""
    return LocalizedStr(
        ru=getattr(obj, f"{field}_ru", None) or fallback,
        kk=getattr(obj, f"{field}_kk", None) or fallback,
        en=getattr(obj, f"{field}_en", None) or fallback,
    )
