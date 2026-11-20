from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-$!bhmha(mmi#ulw$$+i!2v&mpz20dhhr0@81n3ddxik2mbhm20"

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# The development and test servers give each browser connection a thread of its own, and a thread
# keeps a persistent database connection for as long as the browser keeps its connection open: a run
# of browser tests ran the database out of connections. Django's advice: no persistent connections
# with the development server.
DATABASES["default"]["CONN_MAX_AGE"] = 0


try:
    from .local import *
except ImportError:
    pass
