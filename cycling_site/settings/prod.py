import os

from .base import *

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ["RANDOM_SECRET_KEY"]
ALLOWED_HOSTS = [os.environ["VIRTUAL_HOST"]]

STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

try:
    from .local import *
except ImportError:
    pass
