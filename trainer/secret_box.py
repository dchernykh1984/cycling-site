"""Secrets members give the site -- their intervals.icu API keys -- kept sealed with the site's own key.

Fernet (``cryptography``) with ``INTEGRATIONS_ENCRYPTION_KEY`` (issue #471). Without the setting
nothing can be sealed and the features that need it are not offered. A token the key cannot open --
the key was changed or lost -- reads as nothing, so the member simply connects again.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _box() -> Fernet | None:
    key = settings.INTEGRATIONS_ENCRYPTION_KEY
    if not key:
        return None
    try:
        return Fernet(key)
    except (TypeError, ValueError):  # not 32 url-safe base64 bytes: as good as no key
        return None


def available() -> bool:
    """The site can seal what members give it."""
    return _box() is not None


def seal(text: str) -> str:
    box = _box()
    if box is None:
        raise RuntimeError("INTEGRATIONS_ENCRYPTION_KEY is not set")
    return box.encrypt(text.encode()).decode()


def open_sealed(token: str) -> str | None:
    """The text sealed in ``token``, or None when this site's key cannot open it."""
    box = _box()
    if box is None or not token:
        return None
    try:
        return box.decrypt(token.encode()).decode()
    except InvalidToken:
        return None
