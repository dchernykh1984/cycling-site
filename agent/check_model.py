"""Whether the LLM provider still serves the model the agents call, without spending a token.

The agents name their model in code (``DEFAULT_LLM_MODEL``) and call it every night; a provider that
retires the name fails them all. The provider's list of models -- ``GET {LLM_BASE_URL}/models``, which
DeepSeek and the other OpenAI-compatible APIs answer for free -- says whether the name is still there,
so the pipeline of each pull request checks it and the problem shows up before the night does.

    LLM_API_KEY=... LLM_BASE_URL=https://api.deepseek.com python -m agent.check_model
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError

from agent.config import DEFAULT_LLM_MODEL


def model_ids(payload: dict) -> set[str]:
    """The model ids in a ``/models`` answer: ``{"object": "list", "data": [{"id": ...}, ...]}``."""
    return {item["id"] for item in payload.get("data") or [] if isinstance(item, dict) and item.get("id")}


def served_models(base_url: str, api_key: str, timeout: int = 20) -> set[str]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return model_ids(json.load(response))


def main(env=os.environ) -> int:
    """0 when the model is served or the check cannot run here; 1 when the provider says it is not."""
    api_key, base_url = env.get("LLM_API_KEY"), env.get("LLM_BASE_URL")
    if not api_key or not base_url:
        # A pull request from Dependabot or a fork gets no secrets: nothing to ask with.
        print("::warning::LLM_API_KEY or LLM_BASE_URL is not set, so the model was not checked")
        return 0
    model = env.get("LLM_MODEL") or DEFAULT_LLM_MODEL
    try:
        served = served_models(base_url, api_key)
    except HTTPError as exc:
        print(f"::error::the provider refused the list of models: HTTP {exc.code} (is LLM_API_KEY still valid?)")
        return 1
    except (URLError, TimeoutError) as exc:
        # The provider out of reach for a moment says nothing about the model; do not hold the pull request.
        print(f"::warning::the list of models could not be read ({exc}), so the model was not checked")
        return 0
    if model in served:
        print(f"{model} is served")
        return 0
    print(f"::error::{model} is not among the models the provider serves now: {', '.join(sorted(served)) or 'none'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
