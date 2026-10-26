"""Reading a Dropbox folder shared "anyone with the link", with the site's own app credentials.

App authentication (the app key and secret) is all these calls need: no organizer hands over a token.
Tests replace the module-level ``adapter`` (see ``get_adapter``) and never reach Dropbox.
"""

import base64
import json
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.utils.module_loading import import_string

_FOLDER_LINK = re.compile(r"^https://www\.dropbox\.com/scl/fo/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\?")
_TIMEOUT = 20


class DropboxError(Exception):
    def __init__(self, kind: str, detail: str = "", retry_after: int | None = None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.retry_after = retry_after


def is_folder_link(url: str) -> bool:
    return bool(_FOLDER_LINK.match(url or ""))


def clean_folder_link(url: str) -> str:
    """The link without per-visit parameters (`dl`, `e`, `preview`): rlkey and st are what grant access."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k in ("rlkey", "st")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def preview_url(folder_url: str, file_name: str) -> str:
    """Dropbox's own address for one file of a shared folder: opens it, with download, signed out."""
    return f"{folder_url}&dl=0&preview={quote(file_name)}"


class DropboxAdapter:
    def _call(self, url: str, *, body: dict | None = None, arg: dict | None = None) -> bytes:
        if not (settings.DROPBOX_APP_KEY and settings.DROPBOX_APP_SECRET):
            raise DropboxError("unavailable", "the site has no Dropbox app configured")
        token = base64.b64encode(f"{settings.DROPBOX_APP_KEY}:{settings.DROPBOX_APP_SECRET}".encode()).decode()
        headers = {"Authorization": f"Basic {token}"}
        if arg is not None:
            headers["Dropbox-API-Arg"] = json.dumps(arg)  # ensure_ascii keeps the header ASCII
        try:
            response = requests.post(url, json=body, headers=headers, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise DropboxError("unavailable", type(exc).__name__) from None
        if response.status_code == 200:
            return response.content
        if response.status_code == 429:
            retry = response.headers.get("Retry-After")
            raise DropboxError("throttled", retry_after=int(retry) if retry and retry.isdigit() else None)
        text = response.text[:200]
        if response.status_code == 409 and "not_found" in text:
            raise DropboxError("not-found")
        if response.status_code in (401, 403) or "shared_link_access_denied" in text:
            raise DropboxError("forbidden")
        if response.status_code == 409:
            raise DropboxError("invalid-link", text)
        raise DropboxError("unavailable", f"HTTP {response.status_code}")

    def read_file(self, folder_url: str, path: str) -> bytes:
        return self._call(
            "https://content.dropboxapi.com/2/sharing/get_shared_link_file", arg={"url": folder_url, "path": "/" + path}
        )

    def thumbnail(self, folder_url: str, path: str) -> bytes:
        return self._call(
            "https://content.dropboxapi.com/2/files/get_thumbnail_v2",
            arg={
                "resource": {".tag": "link", "url": folder_url, "path": "/" + path},
                "format": "jpeg",
                "size": "w256h256",
                "mode": "bestfit",
            },
        )


def get_adapter():
    return import_string(settings.EVENT_PHOTOS_ADAPTER)()
