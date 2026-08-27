"""Telling search engines about a page the moment it is published.

The classic sitemap ping is gone: Google retired its endpoint in June 2023 (404 today) and Bing's
answers 410. What is alive is IndexNow, which Bing, Yandex and Seznam share -- and Yandex is the
one that matters most for a Kazakh and Russian audience. Google has no equivalent; for Google the
sitemap and internal linking are the whole lever.

Nothing here is allowed to affect the visitor whose action triggered it. The submission happens
after the transaction commits, on a background thread, and any failure is logged and dropped: a
search engine being unreachable must never turn an approval into an error page.
"""

import logging
import threading

import requests
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT = 10

#: One submission carries at most this many URLs, which is far above anything we send at once.
MAX_URLS = 10000


def _key() -> str:
    return (getattr(settings, "INDEXNOW_KEY", "") or "").strip()


def _base_url() -> str:
    return (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")


def key_file_body() -> str:
    """The contents of `/<key>.txt`, which is how the engine verifies we own the host."""
    return _key()


def absolute(path: str) -> str:
    base = _base_url()
    return f"{base}{path}" if path.startswith("/") else path


def _post(urls: list[str], key: str, host: str) -> None:
    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"{_base_url()}/{key}.txt",
        "urlList": urls[:MAX_URLS],
    }
    try:
        response = requests.post(ENDPOINT, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:  # pragma: no cover - network failure path
        logger.warning("IndexNow submission failed: %s", exc)
        return
    if response.status_code >= 400:
        logger.warning("IndexNow refused %s URLs: %s %s", len(urls), response.status_code, response.text[:200])
    else:
        logger.info("IndexNow accepted %s URLs (%s)", len(urls), response.status_code)


def submit(paths: list[str]) -> None:
    """Announce these pages once the surrounding transaction has committed.

    Silently does nothing without a key configured, which is the state in tests and in local
    development -- there is no host to verify there, and no reason to talk to anyone.
    """
    key = _key()
    base = _base_url()
    if not key or not base or not paths:
        return
    host = base.split("//", 1)[-1].split("/", 1)[0]
    urls = [absolute(path) for path in paths]

    def announce() -> None:
        threading.Thread(target=_post, args=(urls, key, host), daemon=True).start()

    transaction.on_commit(announce)


def submit_object(obj) -> None:
    """Announce one published object, by its own URL."""
    url = getattr(obj, "get_absolute_url", None)
    if url is None:
        return
    submit([url()])


def _competition_is_public(competition) -> bool:
    return (
        competition.status == competition.Status.APPROVED and not competition.is_hidden and not competition.is_deleted
    )


def _article_is_public(article) -> bool:
    return not article.is_hidden and not article.is_deleted


#: Which models are worth announcing, and what makes one of them publicly visible.
#: (app_label, model_name, predicate)
WATCHED = [
    ("calendar_app", "Competition", _competition_is_public),
    ("news", "NewsArticle", _article_is_public),
    ("knowledge", "KnowledgeArticle", _article_is_public),
]


def _make_handler(is_public, name):
    def handler(sender, instance, **kwargs):
        # Also fires on an edit, which is what we want: the page changed, so the copy an engine
        # holds is stale. A save that hides or deletes the page announces nothing -- there is no
        # "forget this" in the protocol, and the crawler will find the 404 on its own.
        if is_public(instance):
            submit_object(instance)

    handler.__name__ = f"indexnow_{name}"
    return handler


def connect_signals() -> None:
    """Announce every published page as it is saved, whoever saved it.

    Wired to the model rather than to a view because a competition reaches the public through
    several doors -- the moderation screen, the admin, and the API the import agent posts to --
    and a page published through any of them is equally worth announcing.
    """
    from django.apps import apps
    from django.db.models.signals import post_save

    for app_label, model_name, is_public in WATCHED:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:  # pragma: no cover - only if an app is removed
            continue
        post_save.connect(
            _make_handler(is_public, f"{app_label}_{model_name}"),
            sender=model,
            dispatch_uid=f"indexnow_{app_label}_{model_name}",
            weak=False,
        )
