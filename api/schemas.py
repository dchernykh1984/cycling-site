"""Shared schema types used across multiple API endpoints."""

from ninja import Schema


class LocalizedStr(Schema):
    """A string value with translations for all three supported locales."""

    ru: str = ""
    kk: str = ""
    en: str = ""
