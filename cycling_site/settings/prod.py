import os

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
EMAIL_HOST = "smtp.resend.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "resend"
EMAIL_HOST_PASSWORD = os.environ.get("RESEND_API_KEY", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", f"noreply@{os.environ.get('VIRTUAL_HOST', 'localhost')}")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "ERROR"},
    },
}

try:
    from .local import *
except ImportError:
    pass
