"""Call an OpenAI-compatible chat API (DeepSeek by default) to extract events. Coverage-omitted I/O.

Returns the model's raw reply; agent.pipeline.parse_candidates turns it into Candidate objects, so
the (error-prone) parsing stays pure and unit-tested.
"""

from __future__ import annotations

import json
import urllib.request

from agent.config import Config
from agent.models import KnownEvents, Source

_SYSTEM = (
    "You extract real, upcoming cycling competitions from the given source text. "
    'Return ONLY a JSON array; each item: {"title": str, "date_start": "YYYY-MM-DD", '
    '"date_end": "YYYY-MM-DD"|null, "description": str}. '
    "Title and description in Russian. Include only concrete events with a real date. "
    "If there are none, return []. Do not invent events."
)


def _prompt(text: str, source: Source, guidance: str, known: KnownEvents) -> str:
    rejected = "\n".join(f"- {r['title']} ({r['date_start']}): {r['reason']}" for r in known.rejected[:40])
    return (
        f"Guidance from the maintainers:\n{guidance.strip() or '(none)'}\n\n"
        f"Do NOT propose events similar to these previously rejected ones:\n{rejected or '(none)'}\n\n"
        f"Source: {source.fetch_url}\n"
        f"Source text:\n{text}"
    )


def extract_raw(text: str, source: Source, guidance: str, known: KnownEvents, config: Config) -> str:
    payload = {
        "model": config.llm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(text, source, guidance, known)},
        ],
        "temperature": 0,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{config.llm_base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {config.llm_api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode())
    return body["choices"][0]["message"]["content"]
