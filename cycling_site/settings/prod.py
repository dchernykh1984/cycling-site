import os
from pathlib import Path

import dj_database_url

from ..logconfig import build_logging_config
from .base import *

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ["RANDOM_SECRET_KEY"]

# CodeRed sets VIRTUAL_HOST to the site's domain(s); with several domains attached it can hold more
# than one host (comma/space separated). Parse them all, and always include the team domain so the
# site answers on both cycling.codered.cloud and universalbicycle.team.
_VIRTUAL_HOSTS = os.environ.get("VIRTUAL_HOST", "").replace(",", " ").split()
_EXTRA_HOSTS = ["universalbicycle.team", "www.universalbicycle.team"]
ALLOWED_HOSTS = list(dict.fromkeys(_VIRTUAL_HOSTS + _EXTRA_HOSTS))

# Canonical host for absolute URLs (emails, sitemap, Wagtail admin links). Override with PRIMARY_HOST
# to promote the team domain later; defaults to the first VIRTUAL_HOST, then the CodeRed subdomain.
PRIMARY_HOST = os.environ.get("PRIMARY_HOST") or (_VIRTUAL_HOSTS[0] if _VIRTUAL_HOSTS else "cycling.codered.cloud")

# Django 4+ validates the Origin header on secure POSTs against this list (admin, forms).
CSRF_TRUSTED_ORIGINS = [f"https://{_h}" for _h in ALLOWED_HOSTS]

# Only send session and CSRF cookies over HTTPS. CodeRed Cloud serves the site
# over HTTPS, so this is safe. See Django's deployment checklist:
# https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/#https
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HTTPS hardening (review #5). CodeRed terminates TLS and forwards the original
# scheme via X-Forwarded-Proto, so trust that header and redirect any HTTP request
# to HTTPS; advertise HSTS so browsers stick to HTTPS. Clears check --deploy W004/W008.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Render (and any host that provides a single connection string) sets DATABASE_URL; CodeRed Cloud
# instead exposes discrete DB_* vars. Prefer DATABASE_URL when present and fall back to DB_*, so the
# same prod settings deploy unchanged on both hosts. Both connections require SSL.
if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(conn_max_age=600, ssl_require=True),
    }
else:
    # CodeRed Cloud: https://www.codered.cloud/docs/django/environment/
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

WAGTAILADMIN_BASE_URL = f"https://{PRIMARY_HOST}"
SITE_BASE_URL = f"https://{PRIMARY_HOST}"

# Render serves no static files itself (CodeRed does), so serve them from the app via WhiteNoise:
# the middleware (right after SecurityMiddleware) handles requests, the storage backend hashes and
# compresses assets. Both are harmless on CodeRed, keeping one prod config for both hosts.
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
        "whitenoise.middleware.WhiteNoiseMiddleware",
    )
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media can live on a mounted persistent disk (Render) via MEDIA_ROOT; defaults to the repo's
# media/ directory, as on CodeRed.
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media")))

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", f"noreply@{PRIMARY_HOST}")

# Write logs under BASE_DIR (=/www in prod) so they are reachable via `cr download`;
# SFTP is jailed to /www and the old /data/logs default could not be fetched on this plan.
_LOG_DIR = Path(os.environ.get("LOG_DIR", str(BASE_DIR / "logs")))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = build_logging_config(_LOG_DIR)

# Email 500s to the site admins. SMTP is configured above; SERVER_EMAIL must be the
# authenticated Gmail sender or Gmail rejects the message, so it defaults to the same
# mailbox the site already sends from. Override recipients via the ADMINS env var
# (comma-separated emails) and the sender via SERVER_EMAIL.
ADMINS = [_e.strip() for _e in os.environ.get("ADMINS", DEFAULT_FROM_EMAIL).split(",") if _e.strip()]
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

try:
    from .local import *
except ImportError:
    pass
