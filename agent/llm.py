"""Call an OpenAI-compatible chat API (DeepSeek by default) to extract events. Coverage-omitted I/O.

Returns the model's raw reply; agent.pipeline.parse_candidates turns it into Candidate objects, so
the (error-prone) parsing stays pure and unit-tested.
"""

from __future__ import annotations

import json
import urllib.request

from agent.config import Config
from agent.models import Candidate, KnownEvents, Source, Taxonomy

_LOC = '{"ru": str, "kk": str, "en": str}'
_SYSTEM = (
    "You extract real, upcoming cycling competitions from the given source text. "
    'Return ONLY a JSON array; each item: {"title": ' + _LOC + ', "date_start": "YYYY-MM-DD", '
    '"date_end": "YYYY-MM-DD"|null, "description": ' + _LOC + ', "source_url": str, '
    '"url_route": str, "url_registration": str, "event_type_id": int|null, "discipline_ids": [int], '
    '"country": str, "region": str, "city": str, "venue": ' + _LOC + ', "lat": float|null, "lng": float|null}. '
    "title, description and venue MUST be given in all three locales -- ru (Russian), kk (Kazakh) "
    "and en (English); translate faithfully, and if you cannot translate one, repeat the Russian "
    "text in that field. Write each description as simple HTML (<p>, <br>, <ul>/<ol>/<li>, <strong>) "
    "so the distances, categories/groups, schedule and fees are readable -- never <script>, <style> "
    "or <iframe>. Put the route / GPS-track link (e.g. a Strava link) in url_route and the "
    "registration/signup link in url_registration; source_url is the announcement page on the "
    'organizer\'s own site (not an aggregator). The source text ends with a "Links on the page" '
    "list of the page's real URLs -- pick source_url, url_route and url_registration ONLY from those "
    'real links (or leave ""); never invent or guess a URL, and prefer the most specific event page. '
    "date_start MUST come from the text -- if the date is "
    "only shown in an image/poster you cannot read, do NOT guess it, omit the event instead. Choose "
    "event_type_id and discipline_ids ONLY from the provided lists of ids; if unsure use null / []. "
    "For location, fill country/region/city and the specific start venue/address when given (lat/lng "
    'only if you are sure); leave a field "" when unknown -- do not guess. Follow the maintainer '
    "guidance below. Include only concrete events with a real date. If there are none, return []. "
    "Do not invent events."
)


def _prompt(text: str, source: Source, guidance: str, known: KnownEvents, taxonomy: Taxonomy) -> str:
    existing = "\n".join(f"- {e['title']} ({e['date_start']})" for e in known.existing[:200])
    rejected = "\n".join(f"- {r['title']} ({r['date_start']}): {r['reason']}" for r in known.rejected[:40])
    event_types = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.event_types)
    disciplines = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.disciplines)
    return (
        f"Guidance from the maintainers:\n{guidance.strip() or '(none)'}\n\n"
        f"Event types (id=name): {event_types or '(none)'}\n"
        f"Disciplines (id=name): {disciplines or '(none)'}\n\n"
        f"Events already on the site or already proposed in this run -- do NOT propose any of these "
        f"again, even if the wording, language or year differs:\n{existing or '(none)'}\n\n"
        f"Do NOT propose events similar to these previously rejected ones:\n{rejected or '(none)'}\n\n"
        f"Source: {source.fetch_url}\n"
        f"Source text:\n{text}"
    )


def _chat(system: str, user: str, config: Config) -> str:
    payload = {
        "model": config.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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


def extract_raw(
    text: str, source: Source, guidance: str, known: KnownEvents, taxonomy: Taxonomy, config: Config
) -> str:
    return _chat(_SYSTEM, _prompt(text, source, guidance, known, taxonomy), config)


_ENRICH_SYSTEM = (
    "You are given ONE cycling event we already extracted (as JSON) and the full text of that "
    "event's own web page. Return ONLY a JSON array containing a SINGLE improved version of the "
    "SAME event, using exactly the same schema as the extraction. Use the page to fill in and "
    "correct the fields: a well-formatted HTML description (distances, categories/groups, schedule, "
    "fees, who it is for) using only <p>/<br>/<ul>/<ol>/<li>/<strong>/<em>; date_start/date_end; "
    "url_route (route / GPS-track link, e.g. Strava) and url_registration; event_type_id and "
    "discipline_ids from the provided lists; and country/region/city/venue. The page text ends with "
    'a "Links on the page" list -- take url_route, url_registration and a more specific source_url '
    "ONLY from those real links, never invent one, and prefer the specific event page. Keep title, "
    "description "
    "and venue in all three locales (ru/kk/en). Keep it the SAME event -- never turn it into a "
    "different one, and do not invent facts the page does not state. If the page adds nothing, "
    "return the event unchanged."
)


def _event_json(candidate: Candidate) -> str:
    return json.dumps(
        {
            "title": {"ru": candidate.title, "kk": candidate.title_kk, "en": candidate.title_en},
            "date_start": candidate.date_start,
            "date_end": candidate.date_end,
            "description": {
                "ru": candidate.description,
                "kk": candidate.description_kk,
                "en": candidate.description_en,
            },
            "source_url": candidate.source_url,
            "url_route": candidate.url_route,
            "url_registration": candidate.url_registration,
            "event_type_id": candidate.event_type_id,
            "discipline_ids": candidate.discipline_ids,
            "country": candidate.country,
            "region": candidate.region,
            "city": candidate.city,
            "venue": {"ru": candidate.venue, "kk": candidate.venue_kk, "en": candidate.venue_en},
            "lat": candidate.lat,
            "lng": candidate.lng,
        },
        ensure_ascii=False,
    )


def enrich_raw(candidate: Candidate, page_text: str, guidance: str, taxonomy: Taxonomy, config: Config) -> str:
    """Ask the model to refine one event using the full text of its own event page."""
    event_types = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.event_types)
    disciplines = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.disciplines)
    user = (
        f"Guidance from the maintainers:\n{guidance.strip() or '(none)'}\n\n"
        f"Event types (id=name): {event_types or '(none)'}\n"
        f"Disciplines (id=name): {disciplines or '(none)'}\n\n"
        f"Current event (JSON):\n{_event_json(candidate)}\n\n"
        f"Event page text:\n{page_text}"
    )
    return _chat(_ENRICH_SYSTEM, user, config)
