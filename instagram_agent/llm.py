"""The prompt that turns a club's Instagram posts into ride announcements. Coverage-omitted I/O.

The schema is deliberately the one the web agent uses, so the reply is parsed by the same
``agent.pipeline.parse_candidates`` and the events land on the site through the same path.

What is different is what the model is asked to read. A club's feed is mostly *not* announcements:
photo reports from last Saturday's ride, training posts, memes. Telling those apart is the whole
job, and the tell is grammatical -- "we rode", "thank you all who came" is a report; "this Saturday
we ride, gather at 6:15" is an announcement. The second thing that is different is the date: rides
are announced as "this Saturday, 1 August", which is only a date if you know the day the post was
published, so every post is given with its publication date.
"""

from __future__ import annotations

import datetime

from agent import llm
from agent.config import Config
from agent.models import KnownEvents, Taxonomy
from instagram_agent.accounts import Account

_LOC = '{"ru": str, "kk": str, "en": str}'

_SYSTEM = (
    "You read the recent posts of a cycling club's Instagram account and extract the rides and "
    "races it ANNOUNCES. "
    'Return ONLY a JSON array; each item: {"title": ' + _LOC + ', "date_start": "YYYY-MM-DD", '
    '"date_end": "YYYY-MM-DD"|null, "description": ' + _LOC + ', "event_type_id": int|null, '
    '"discipline_ids": [int], "country": str, "region": ' + _LOC + ', "city": ' + _LOC + ", "
    '"venue": ' + _LOC + "}. "
    "\n\n"
    "ONLY ANNOUNCEMENTS. Most posts in a club's feed are not events. A photo report of a ride that "
    'already happened ("we rode", "thank you all who came", "great company today"), a training '
    "post, a results table of a finished championship, an advertisement or a motivational text are "
    "NOT events -- skip them silently. An event is a post inviting people to something that has not "
    "happened yet: it names a day, and usually a meeting place and a time. When a post is about a "
    "start that has already taken place, skip it even if it names the date. "
    "\n\n"
    'DATES. Each post is given with the date it was published. A caption says "this Saturday, '
    '1 August" or "on Monday we ride" -- resolve that against the publication date and return a '
    "real YYYY-MM-DD. Reading a relative date this way is not guessing. If a post names no day at "
    "all, or the day is only legible on an image you cannot read, omit the event rather than "
    "inventing a date. If the announced day is already in the past, omit it. "
    "\n\n"
    "WHAT TO WRITE. title: the ride's own name as the club calls it (\"Early Bird Coffee Ride: UBT "
    'Giant x Medeo"), not a description of it. description: simple HTML (<p>, <br>, <ul>/<li>, '
    "<strong>) carrying what a rider needs -- the meeting time and the start time, the meeting "
    "place, the route, the pace, whether it is open to everyone, the fee, and registration details "
    "if there are any; never <script>, <style> or <iframe>. Keep the club's own wording where it is "
    "concrete, and do not invent details the post does not state. "
    "\n\n"
    "title, description, region, city and venue MUST be given in all three locales -- ru (Russian), "
    "kk (Kazakh) and en (English). Translate faithfully; if you cannot translate one, repeat the "
    "Russian text in that field. "
    "\n\n"
    'PLACE. venue is the meeting point when the post names one ("Giant store, Abay 47"), and the '
    "region and city it sits in. When the post does not say where, use the city the maintainers "
    'gave for this account; leave a field "" when you still do not know -- do not guess. '
    "\n\n"
    "NO LINKS, NO PLATFORM, NO PICTURES. Do not output source_url, url_route or url_registration, "
    "and never name the website or app these posts come from, or link a post on it, anywhere in a "
    "title or a description. Write no images and no embeds either -- no <img>, <video>, <iframe> "
    "or <picture>; a description is text. The event is credited to the account by name and to "
    "nothing else; that credit is added afterwards, so do not write it yourself. "
    "\n\n"
    "Choose event_type_id and discipline_ids ONLY from the provided lists of ids; if unsure use "
    "null / []. A club ride is usually a ride rather than a race -- pick the type that fits. "
    "If the account announced nothing, return []. Do not invent events."
)

_MAX_EXISTING = 120
_MAX_REJECTED = 30


def build_prompt(
    text: str,
    account: Account,
    guidance: str,
    known: KnownEvents,
    taxonomy: Taxonomy,
    today: str = "",
) -> str:
    """The user half of the call: the taxonomy, what the site already knows, and the account's posts."""
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
        f"again, even if the wording, language or year differs. A club's weekly ride is a NEW event "
        f"each week, so only the one on the SAME DAY as a listed event is a repeat:\n"
        f"{existing or '(none)'}\n\n"
        f"Do NOT propose events similar to these previously rejected ones:\n{rejected or '(none)'}\n\n"
        f"{text}"
    )


def extract_raw(
    text: str,
    account: Account,
    guidance: str,
    known: KnownEvents,
    taxonomy: Taxonomy,
    config: Config,
    today: str = "",
) -> str:
    return llm.chat(_SYSTEM, build_prompt(text, account, guidance, known, taxonomy, today), config)
