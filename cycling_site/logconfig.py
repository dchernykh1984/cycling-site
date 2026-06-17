"""Logging configuration shared by the settings modules.

Kept as a plain function returning a ``dictConfig`` dict so it can be imported and
asserted in tests without importing a settings module (which needs prod env vars).
"""

from pathlib import Path


def build_logging_config(log_dir: Path) -> dict:
    """Build the production logging config writing to ``log_dir/django.log``.

    Besides the rotating file + console handlers, request errors (HTTP 500s) are
    emailed to ``settings.ADMINS`` via Django's ``AdminEmailHandler`` (only when
    ``DEBUG`` is false), so failures surface even when the log file is hard to fetch.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "require_debug_false": {
                "()": "django.utils.log.RequireDebugFalse",
            },
        },
        "formatters": {
            "verbose": {
                "format": "{asctime} {levelname} {name} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(log_dir / "django.log"),
                "when": "midnight",
                "backupCount": 14,
                "encoding": "utf-8",
                "formatter": "verbose",
            },
            "mail_admins": {
                "class": "django.utils.log.AdminEmailHandler",
                "level": "ERROR",
                "filters": ["require_debug_false"],
                "include_html": True,
            },
        },
        "root": {"handlers": ["console", "file"], "level": "WARNING"},
        "loggers": {
            "django": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
            "django.request": {
                "handlers": ["console", "file", "mail_admins"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.security": {
                "handlers": ["console", "file", "mail_admins"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }
