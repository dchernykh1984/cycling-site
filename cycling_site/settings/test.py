from .dev import *

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Disable caching in tests so the live server never serves stale SiteContent
# that was cached by a previous test's requests but since flushed from the DB.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}

# No test reaches the model: a key from a developer's .env would offer the chat everywhere, and the
# tests that need it set a key of their own and replace the call.
ASSISTANT_LLM_API_KEY = ""
