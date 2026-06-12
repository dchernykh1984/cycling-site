"""Shared schema types used across multiple API endpoints."""

from typing import Any

from ninja import Schema


class LocalizedStr(Schema):
    """A string value with translations for all three supported locales."""

    ru: str = ""
    kk: str = ""
    en: str = ""


def localize_field(obj: Any, field: str) -> LocalizedStr:
    return LocalizedStr(
        ru=getattr(obj, f"{field}_ru", None) or "",
        kk=getattr(obj, f"{field}_kk", None) or "",
        en=getattr(obj, f"{field}_en", None) or "",
    )
