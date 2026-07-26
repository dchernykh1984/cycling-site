"""Call an OpenAI-compatible chat API (DeepSeek by default) to extract events. Coverage-omitted I/O.

Returns the model's raw reply; agent.pipeline.parse_candidates turns it into Candidate objects, so
the (error-prone) parsing stays pure and unit-tested.
"""

from __future__ import annotations

import datetime
import json
import urllib.request

from agent.config import Config
from agent.models import Candidate, KnownEvents, Source, Taxonomy

_LOC = '{"ru": str, "kk": str, "en": str}'
_SYSTEM = (
    "You extract real, upcoming sporting competitions from the given source text -- cycling "
    "first, and also running, triathlon and cross-country skiing. The instructions below say "
    "which ones matter and in what order; follow them rather than assuming a single sport. "
    'Return ONLY a JSON array; each item: {"title": ' + _LOC + ', "date_start": "YYYY-MM-DD", '
    '"date_end": "YYYY-MM-DD"|null, "description": ' + _LOC + ', "source_url": str, '
    '"url_route": str, "url_registration": str, "event_type_id": int|null, "discipline_ids": [int], '
    '"country": str, "region": '
    + _LOC
    + ', "city": '
    + _LOC
    + ', "venue": '
    + _LOC
    + ', "lat": float|null, "lng": float|null}. '
    "title, description, region, city and venue MUST be given in all three locales -- ru (Russian), "
    "kk (Kazakh) "
    "and en (English); translate faithfully, and if you cannot translate one, repeat the Russian "
    "text in that field. Write each description as simple HTML (<p>, <br>, <ul>/<ol>/<li>, <strong>) "
    "so the distances, categories/groups, schedule and fees are readable -- never <script>, <style> "
    "or <iframe>. Put the route / GPS-track link (e.g. a Strava link) in url_route and the "
    "registration/signup link in url_registration; source_url is the announcement page on the "
    'organizer\'s own site (not an aggregator). The source text ends with a "Links on the page" '
    'list of the page\'s real links, each written as "name - url" where the name is the text the '
    "link is shown under -- use that name to tell which race a link belongs to and give each event "
    "the link that names it. Pick source_url, url_route and url_registration ONLY from those real "
    'links (or leave ""); never invent or guess a URL, and prefer the most specific event page. '
    "date_start MUST come from the text -- if the date is "
    "only shown in an image/poster you cannot read, do NOT guess it, omit the event instead. In a "
    "calendar or list a date is often a month/section heading with a day number in each row below it "
    "-- combine that heading with the row's day to form date_start (reading it this way is not "
    "guessing). Choose "
    "event_type_id and discipline_ids ONLY from the provided lists of ids; if unsure use null / []. "
    "For location, fill country/region/city and the specific start venue/address when given (lat/lng "
    'only if you are sure); leave a field "" when unknown -- do not guess. Follow the maintainer '
    "guidance below. Include only concrete events with a real date. If there are none, return []. "
    "Do not invent events."
)


# Per-type framing so the model treats each source deterministically (esp. aggregators, where
# source_url must be the organizer's own page and not the calendar we found the race on).
_KIND_GUIDANCE = {
    "aggregator": (
        "This page is an events AGGREGATOR / calendar listing many races from different organizers -- "
        "often a dense list or table with one race per line/row. Go through it row by row and extract "
        "EVERY upcoming competition, even the ones on a single terse line; do not stop early or skip a "
        "race because its row is brief. A calendar of RUNNING events, or of events in far-away "
        "countries, is IN SCOPE just like a cycling one -- running, triathlon and skiing all count, "
        "and a foreign location is never a reason to skip a real event; extract them all the same. "
        "Give each race the link that names it in the 'Links on the page' list: the organizer's own "
        "page for that race when the list has one, otherwise the race's own entry page on this "
        "calendar (a per-race link, e.g. one ending in a race id). What must NEVER be used is the "
        "calendar's own listing URL, which names no single race -- if this race has no link of its "
        'own in the list, leave source_url "" rather than falling back to the listing.'
    ),
    "organizer": (
        "This page belongs to a single event ORGANIZER; extract their real upcoming competitions and "
        "set source_url to the specific event's page on this same site."
    ),
    "tg_public": (
        "This is the recent post feed of a public TELEGRAM channel; extract real upcoming "
        "competitions from the posts. Prefer the organizer's own event page for source_url when a "
        "post links one; otherwise use the specific post link."
    ),
}


_MAX_EXISTING = 200
_MAX_REJECTED = 40


def _for_prompt(items: list[dict], limit: int, today: str) -> list[dict]:
    """The known events worth spending prompt room on: the ones a run could still propose.

    The site carries far more events than fit here -- 374 approved in July 2026, only 189 of them
    upcoming -- and a run never proposes a past event, so filling the list from the top spends most
    of the room on events that can never be duplicated and leaves real upcoming ones unmentioned.
    Upcoming first, soonest first; past ones fill whatever room is left, most recent first.
    """
    upcoming = sorted((item for item in items if item.get("date_start", "") >= today), key=_date_start)
    past = sorted((item for item in items if item.get("date_start", "") < today), key=_date_start, reverse=True)
    return (upcoming + past)[:limit]


def _date_start(item: dict) -> str:
    return item.get("date_start", "")


def _prompt(text: str, source: Source, guidance: str, known: KnownEvents, taxonomy: Taxonomy, today: str = "") -> str:
    today = today or datetime.date.today().isoformat()
    existing = "\n".join(
        f"- {e['title']} ({e['date_start']})" for e in _for_prompt(known.existing, _MAX_EXISTING, today)
    )
    rejected = "\n".join(
        f"- {r['title']} ({r['date_start']}): {r['reason']}" for r in _for_prompt(known.rejected, _MAX_REJECTED, today)
    )
    event_types = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.event_types)
    disciplines = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.disciplines)
    kind_note = _KIND_GUIDANCE.get(source.kind, "(generic web page)")
    source_hint = f"Source-specific hint: {source.hint.strip()}\n" if source.hint.strip() else ""
    return (
        f"Guidance from the maintainers:\n{guidance.strip() or '(none)'}\n\n"
        f"Event types (id=name): {event_types or '(none)'}\n"
        f"Disciplines (id=name): {disciplines or '(none)'}\n\n"
        f"Events already on the site or already proposed in this run -- do NOT propose any of these "
        f"again, even if the wording, language or year differs:\n{existing or '(none)'}\n\n"
        f"Do NOT propose events similar to these previously rejected ones:\n{rejected or '(none)'}\n\n"
        f"Source type ({source.kind}): {kind_note}\n"
        f"{source_hint}"
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
    "You are given ONE sporting event we already extracted (as JSON) and the full text of that "
    "event's own web page. Return ONLY a JSON array containing a SINGLE improved version of the "
    "SAME event, using exactly the same schema as the extraction. Use the page to fill in and "
    "correct the fields: a well-formatted HTML description (distances, categories/groups, schedule, "
    "fees, who it is for) using only <p>/<br>/<ul>/<ol>/<li>/<strong>/<em>; date_start/date_end; "
    "url_route (route / GPS-track link, e.g. Strava) and url_registration; event_type_id and "
    "discipline_ids from the provided lists; and country/region/city/venue. The page text ends with "
    'a "Links on the page" list, each shown as "name - url" -- take url_route, url_registration and '
    "a more specific source_url ONLY from those real links, never invent one, and prefer the "
    "specific event page. If the page you were given is a shared calendar's entry for the race "
    "rather than the organizer's own announcement, set source_url to the organizer's own page for "
    "this race from that list (the site the entry credits or links out to); a calendar entry is a "
    "second-hand copy and is often out of date or plain wrong about the name and place. Keep title, "
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
