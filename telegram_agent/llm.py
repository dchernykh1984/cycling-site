"""The prompt that turns a Telegram channel's messages into event announcements. Coverage-omitted I/O.

The schema is deliberately the one the other agents use, so the reply is parsed by the same
``agent.pipeline.parse_candidates`` and the events land on the site through the same path.

Two things are specific to this reader. The messages come from private channels and closed
communities, so the model is told to never name or link the channel anywhere -- the site must not
disclose where a private announcement was read. And a group chat is a conversation, not a feed:
the announcement sits between "who is coming?" and route bickering, so telling an announcement from
talk *about* one matters more here than anywhere.
"""

from __future__ import annotations

import datetime

from agent import llm
from agent.config import Config
from agent.models import KnownEvents, Taxonomy
from telegram_agent.channels import Channel

_LOC = '{"ru": str, "kk": str, "en": str}'

_SYSTEM = (
    "You read the recent messages of a local sports community's Telegram channel or group chat -- "
    "cycling, running, hiking, skiing, any outdoor sport -- and extract the events it ANNOUNCES: "
    "rides, runs, hikes, walks, ascents, races, group outings. "
    'Return ONLY a JSON array; each item: {"title": ' + _LOC + ', "date_start": "YYYY-MM-DD", '
    '"date_end": "YYYY-MM-DD"|null, "description": ' + _LOC + ', "url_registration": str, '
    '"event_type_id": int|null, '
    '"discipline_ids": [int], "country": str, "region": ' + _LOC + ', "city": ' + _LOC + ", "
    '"venue": ' + _LOC + "}. "
    "\n\n"
    "WHAT COUNTS AS AN EVENT. The activity itself must be the sport -- riding, running, hiking, "
    "walking, skiing, swimming -- done under the participants' own power. Getting somewhere by "
    "car is not: a trip where people drive out and camp, a carpool with the fuel split, a picnic "
    "or a party is not an event for this calendar however well it names a day. Nor is a private "
    'arrangement -- "one seat left, details in DM" invites a person, not the public. '
    "\n\n"
    "ONLY ANNOUNCEMENTS. A group chat is mostly conversation: photo reports of the last outing "
    '("we rode", "thank you all who came"), people asking who is coming or how to get somewhere, '
    "route talk, taxi and gear questions, items for sale, results of a finished start, stickers "
    "and memes. None of those are events -- skip them silently. An event is a message inviting "
    "people to something that has not happened yet: it names a day, and usually a meeting place "
    "and a time. A reply discussing an announced event is not a second event. When a message is "
    "about a start that already took place, skip it even if it names the date. "
    "\n\n"
    'DATES. Each message is given with the date it was published. A message says "this Saturday" '
    'or "tomorrow at 7" -- resolve that against the publication date and return a real '
    "YYYY-MM-DD. Reading a relative date this way is not guessing. If a message names no day at "
    "all, or the day is only legible on an image you cannot read, omit the event rather than "
    "inventing a date. If the announced day is already in the past, omit it. "
    "\n\n"
    "WHAT TO WRITE. title: the event's own name as the community calls it, not a description of "
    "it. description: simple HTML (<p>, <br>, <ul>/<li>, <strong>) carrying what a participant "
    "needs -- the meeting time and the start time, the meeting place, the route, the pace or "
    "difficulty, whether it is open to everyone, the fee, and registration details if there are "
    "any; never <script>, <style> or <iframe>. Keep the community's own wording where it is "
    "concrete, and do not invent details the message does not state. "
    "\n\n"
    "title, description, region, city and venue MUST be given in all three locales -- ru (Russian), "
    "kk (Kazakh) and en (English). Translate faithfully; if you cannot translate one, repeat the "
    "Russian text in that field. "
    "\n\n"
    'PLACE. venue is the meeting point when the message names one ("parking at Halyk Bank, '
    'Al-Farabi 40"), and the region and city it sits in. When the message does not say where, use '
    'the city the maintainers gave for this channel; leave a field "" when you still do not know '
    "-- do not guess. "
    "country is the country's NAME as people write it, in Russian -- "
    '"Kazakhstan" spelled out, never a code like "KZ" or "RU": the site matches geography by name, '
    "and a code puts the event on the calendar with no place at all. "
    "\n\n"
    "NEVER NAME THE SOURCE YOURSELF. These messages come from private channels and closed "
    "communities. Do not name the channel, do not link it, and do not write any 'source' or "
    "credit line anywhere in a title or a description -- the source credit is appended "
    "afterwards, in code, and only there. Do not output source_url or url_route. "
    "url_registration may carry a registration link ONLY when the announcement itself gives an "
    "external one (a form, a race site); never a t.me link. Write no images and no embeds -- no "
    "<img>, <video>, <iframe> or <picture>; a description is text. "
    "\n\n"
    "Choose event_type_id and discipline_ids ONLY from the provided lists of ids; if unsure use "
    "null / []. The lists cover more than cycling -- running, ski racing, hiking and more; a "
    "community outing is usually a training/leisure event rather than a race, and a hike belongs "
    "to the hiking disciplines -- pick what fits. "
    "If the channel announced nothing, return []. Do not invent events."
)

_MAX_EXISTING = 120
_MAX_REJECTED = 30


def build_prompt(
    text: str,
    channel: Channel,
    guidance: str,
    known: KnownEvents,
    taxonomy: Taxonomy,
    today: str = "",
) -> str:
    """The user half of the call: the taxonomy, what the site already knows, and the channel's messages."""
    today = today or datetime.date.today().isoformat()
    existing = "\n".join(
        f"- {e['title']} ({e['date_start']})" for e in llm.upcoming_first(known.existing, _MAX_EXISTING, today)
    )
    rejected = "\n".join(
        f"- {r['title']} ({r['date_start']}): {r['reason']}"
        for r in llm.upcoming_first(known.rejected, _MAX_REJECTED, today)
    )
    event_types = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.event_types)
    disciplines = ", ".join(f"{item['id']}={item['name']}" for item in taxonomy.disciplines)
    return (
        f"Guidance from the maintainers:\n{guidance.strip() or '(none)'}\n\n"
        f"Event types (id=name): {event_types or '(none)'}\n"
        f"Disciplines (id=name): {disciplines or '(none)'}\n\n"
        f"Events already on the site or already proposed in this run -- do NOT propose any of these "
        f"again, even if the wording, language or year differs. A community's weekly outing is a "
        f"NEW event each week, so only the one on the SAME DAY as a listed event is a repeat:\n"
        f"{existing or '(none)'}\n\n"
        f"Do NOT propose events similar to these previously rejected ones:\n{rejected or '(none)'}\n\n"
        f"{text}"
    )


def extract_raw(
    text: str,
    channel: Channel,
    guidance: str,
    known: KnownEvents,
    taxonomy: Taxonomy,
    config: Config,
    today: str = "",
) -> str:
    return llm.chat(_SYSTEM, build_prompt(text, channel, guidance, known, taxonomy, today), config)
