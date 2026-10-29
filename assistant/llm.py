"""The one call to the language model: an OpenAI-compatible chat API, DeepSeek by default (issue #353).

The key is read from settings and goes only into the request's header. A failure comes back as what
the admin can do about it -- tell the owner, or try again -- never as the provider's own answer.
"""

from __future__ import annotations

import http.client
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from agent.config import DEFAULT_LLM_MODEL

logger = logging.getLogger(__name__)

# A full set of titles, descriptions and link previews measured 764 tokens. Room for a long text in
# two more languages besides, which takes about a minute to write; an answer over it is cut off.
MAX_TOKENS = 16_000
# Under the 100 s the site's proxy waits for a page: past it the reader would get the proxy's error
# page instead of the assistant's own "send it again".
TIMEOUT_SECONDS = 90


class UnavailableError(Exception):
    """The model gave no usable answer; ``reason`` is one of the constants below."""

    NO_KEY = "no_key"
    NO_BALANCE = "no_balance"
    KEY_REFUSED = "key_refused"
    BUSY = "busy"
    BAD_ANSWER = "bad_answer"
    TOO_LONG = "too_long"

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_REASONS = {401: UnavailableError.KEY_REFUSED, 402: UnavailableError.NO_BALANCE, 403: UnavailableError.KEY_REFUSED}


def complete(messages: list[dict]) -> dict:
    """The model's answer to ``messages``, a JSON object; raises UnavailableError."""
    key = settings.ASSISTANT_LLM_API_KEY
    if not key:
        raise UnavailableError(UnavailableError.NO_KEY)
    payload = {
        "model": DEFAULT_LLM_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        # The provider thinks by default. A turn is a question and a few fields, and thinking would
        # multiply its tokens and its wait.
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_TOKENS,
        "temperature": 0.3,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{settings.ASSISTANT_LLM_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise UnavailableError(_REASONS.get(exc.code, UnavailableError.BUSY)) from None
    except (OSError, http.client.HTTPException, ValueError):
        raise UnavailableError(UnavailableError.BUSY) from None
    usage = body.get("usage") or {}
    logger.info(
        "assistant: %s tokens in, %s of them cached, %s out",
        usage.get("prompt_tokens"),
        usage.get("prompt_cache_hit_tokens"),
        usage.get("completion_tokens"),
    )
    try:
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise UnavailableError(UnavailableError.TOO_LONG)
        answer = json.loads(choice["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise UnavailableError(UnavailableError.BAD_ANSWER) from None
    if not isinstance(answer, dict):
        raise UnavailableError(UnavailableError.BAD_ANSWER)
    return answer
