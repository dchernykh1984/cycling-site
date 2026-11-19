"""Startup checks for the virtual ride's settings."""

from django.conf import settings
from django.core import checks


@checks.register()
def integrations_key_can_seal(app_configs, **kwargs):
    """A key that is set but cannot seal anything would hide intervals.icu without a word."""
    from trainer import secret_box

    if not settings.INTEGRATIONS_ENCRYPTION_KEY or secret_box.available():
        return []
    return [
        checks.Warning(
            "INTEGRATIONS_ENCRYPTION_KEY is set but is not a Fernet key (32 url-safe base64-encoded bytes):"
            " intervals.icu is not offered.",
            hint="Generate one: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
            id="trainer.W001",
        )
    ]
