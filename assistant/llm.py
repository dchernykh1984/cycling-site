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

# A turn writes at most the three descriptions with their titles and link previews: 764 tokens when
# measured, so this only stops an answer that runs away.
MAX_TOKENS = 6000
TIMEOUT_SECONDS = 90


class UnavailableError(Exception):
    """The model gave no usable answer; ``reason`` is one of the constants below."""

    NO_KEY = "no_key"
    NO_BALANCE = "no_balance"
    KEY_REFUSED = "key_refused"
    BUSY = "busy"
    BAD_ANSWER = "bad_answer"

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
        answer = json.loads(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise UnavailableError(UnavailableError.BAD_ANSWER) from None
    if not isinstance(answer, dict):
        raise UnavailableError(UnavailableError.BAD_ANSWER)
    return answer
