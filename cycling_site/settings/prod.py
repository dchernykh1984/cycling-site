import os
from pathlib import Path

from .base import *

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ["RANDOM_SECRET_KEY"]
ALLOWED_HOSTS = [os.environ["VIRTUAL_HOST"]]

# Only send session and CSRF cookies over HTTPS. CodeRed Cloud serves the site
# over HTTPS, so this is safe. See Django's deployment checklist:
# https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/#https
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# CodeRed Cloud provides PostgreSQL connection details via these env vars
# (not via DATABASE_URL). The database requires SSL and uses UTF8.
# See https://www.codered.cloud/docs/django/environment/
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "client_encoding": "UTF8",
            "sslmode": "require",
        },
    }
}

WAGTAILADMIN_BASE_URL = f"https://{os.environ['VIRTUAL_HOST']}"
SITE_BASE_URL = f"https://{os.environ['VIRTUAL_HOST']}"

STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", f"noreply@{os.environ.get('VIRTUAL_HOST', 'localhost')}")

_LOG_DIR = Path(os.environ.get("LOG_DIR", "/data/logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
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
            "filename": str(_LOG_DIR / "django.log"),
            "when": "midnight",
            "backupCount": 14,
            "encoding": "utf-8",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["console", "file"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
    },
}

try:
    from .local import *
except ImportError:
    pass
