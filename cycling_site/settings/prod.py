import os

from .base import *

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ["RANDOM_SECRET_KEY"]
ALLOWED_HOSTS = [os.environ["VIRTUAL_HOST"]]

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

STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

try:
    from .local import *
except ImportError:
    pass
