"""What the model is told: the reply's contract, the skills, the site's lists, the conversation and the turn.

What stays the same between turns comes first -- the contract, the skills, the event types and the
disciplines -- and the conversation after it only grows. The provider caches the beginning of a
prompt it has seen, and a turn pays a fiftieth of the price for that part (research R1).
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from assistant.models import Conversation, Message
from calendar_app.models import DisciplineCategory, EventType
from locations.models import Location

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
LANGUAGES = ("ru", "kk", "en")
TEXT_FIELDS = ("title", "description", "preview_text")
URL_FIELDS = ("url_announcement", "url_registration", "url_route", "url_regulations", "url_results")
FILE_FIELDS = ("file_announcement", "file_route", "file_regulations", "file_results")
# How much of a field the model is shown; a description is the longest, and the editor allows far more.
_MAX_TEXT = {"title": 255, "description": 20_000, "preview_text": 300}
_MAX_LINE = 1000

CONTRACT = """\
You are the assistant of a website that lists sporting events: races, rides, runs, hikes and more.
An administrator of the site adds a new event, or edits one, by talking to you: you ask them about
it and fill in the event's form, and they save it with the form's own button.

Answer with ONE json object and nothing else: {"reply": "...", "set": {...}}

"reply" is what you say to the administrator, in the page's language, which each of their messages
names. "set" holds only the fields of the form you change now; leave out the ones that stay as they
are. A field set to "" (or [] for a list) is emptied. The fields:
- "title", "description", "preview_text": each {"ru": "...", "kk": "...", "en": "..."} -- the three
  languages always together. "description" is simple HTML: <p>, <ul>, <ol>, <li>, <strong>, <em>,
  <br>, <a href="...">.
- "date_start", "date_end": "YYYY-MM-DD"; an event of one day has no date_end.
- "event_type_ids", "discipline_ids": lists of ids, only from the lists below.
- "url_announcement", "url_registration", "url_route", "url_regulations", "url_results": links copied
  exactly from the administrator's messages; never one they did not write.
- "place": {"country": "...", "region": "...", "city": "...", "venue": {"ru": "...", "kk": "...",
  "en": "..."}, "lat": null, "lng": null} -- where the event starts, in words, as the administrator
  named it; the site finds it among its own places. "venue" is the exact spot (a shop, an entrance
  to a park, an address), empty when nobody said it. "lat" and "lng" only when the administrator
  wrote the numbers.

The form as it stands comes with each message of the administrator's: trust it over the
conversation, since they may have changed it by hand. A file they attach is already in the form.

The site's instructions follow, in Russian: they say what to ask and how an announcement is written.
"""


def skills() -> str:
    """Every skill file, in the order of their names."""
    return "\n\n".join(path.read_text(encoding="utf-8").strip() for path in sorted(SKILLS_DIR.glob("*.md")))


def _names(item) -> str:
    """An item's Russian and English names, once when they are the same."""
    ru, en = getattr(item, "name_ru", "") or "", getattr(item, "name_en", "") or ""
    return " / ".join(dict.fromkeys(name for name in (ru, en) if name)) or str(item)


def taxonomy() -> str:
    """The event types and the disciplines the model may choose from, with their ids."""
    lines = ["Event types (id: name):"]
    lines += [f"{kind.pk}: {_names(kind)}" for kind in EventType.objects.order_by("order", "pk")]
    lines += ["", "Disciplines, by direction (id: name):"]
    for category in DisciplineCategory.objects.order_by("order", "pk"):
        lines.append(_names(category))
        lines += [
            f"  {discipline.pk}: {_names(discipline)}" for discipline in category.disciplines.order_by("order", "pk")
        ]
    return "\n".join(lines)


def system_prompt() -> str:
    return f"{CONTRACT}\n{skills()}\n\n{taxonomy()}\n"


def _text(value, limit: int = _MAX_LINE) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _ids(value) -> list[int]:
    if not isinstance(value, list):
        return []
    return [int(item) for item in value if str(item).isdigit()][:50]


def _chain(location: Location) -> str:
    """A place as the path to it: country / region / city / venue."""
    nodes = [*location.get_ancestors(), location]
    return " / ".join(node.name_ru or node.name_en or "" for node in nodes)


def _place(raw: dict) -> dict | str:
    """The place the form holds, in words: a venue of the site's, a new venue, or nothing."""
    location_id = str(raw.get("location") or "")
    if location_id.isdigit():
        location = Location.objects.filter(pk=int(location_id), is_deleted=False).first()
        if location is not None:
            if location.is_hidden:
                return f"{_chain(location.get_parent())} (the exact spot not chosen)"
            return _chain(location)
    city_id = str(raw.get("new_venue_city") or "")
    names = {lang: _text(raw.get("new_venue_name" + ("" if lang == "ru" else f"_{lang}"))) for lang in LANGUAGES}
    if city_id.isdigit() and any(names.values()):
        city = Location.objects.filter(pk=int(city_id), is_deleted=False).first()
        point = [_text(raw.get("new_venue_lat")), _text(raw.get("new_venue_lng"))]
        return {
            "new_venue": names,
            "city": _chain(city) if city else "",
            "point": point if all(point) else None,
        }
    return ""


def _existing_file(competition, name: str) -> str:
    stored = getattr(competition, name, None) if competition is not None else None
    return Path(stored.name).name if stored else ""


def describe_form(raw: dict, competition=None) -> dict:
    """The form as the page sent it, in the words of the contract, with the place in names."""
    raw = raw if isinstance(raw, dict) else {}
    form: dict = {
        name: {lang: _text(raw.get(f"{name}_{lang}"), _MAX_TEXT[name]) for lang in LANGUAGES} for name in TEXT_FIELDS
    }
    form["date_start"] = _text(raw.get("date_start"), 10)
    form["date_end"] = _text(raw.get("date_end"), 10)
    form["event_type_ids"] = _ids(raw.get("event_types"))
    form["discipline_ids"] = _ids(raw.get("disciplines"))
    form.update({name: _text(raw.get(name)) for name in URL_FIELDS})
    form["place"] = _place(raw)
    form["files"] = {
        name.removeprefix("file_"): _text(raw.get(name)) or _existing_file(competition, name) for name in FILE_FIELDS
    }
    form["registration_on_the_site"] = raw.get("registration_enabled") is True
    return form


def attachments_line(attachments: list[dict]) -> str:
    """What the administrator attached, for the model."""
    lines = []
    for item in attachments:
        what = "the route file" if item.get("kind") == "route" else "the regulations file"
        line = f'The administrator attached "{item.get("name", "")}"; it is in the form as {what}.'
        start = item.get("start")
        if start:
            line += f" The track starts at {start[0]:.6f}, {start[1]:.6f}."
        lines.append(line)
    return "\n".join(lines)


def turn(
    text: str,
    form: dict,
    attachments: list[dict],
    today: datetime.date,
    language: str,
    *,
    editing: bool,
) -> str:
    """The administrator's message as the model reads it: the day, the page, the form, the files."""
    task = "editing an event already on the site" if editing else "adding a new event"
    parts = [
        f"Today is {today.isoformat()}, {today.strftime('%A')}. The page's language: {language}.",
        f"The administrator is {task}.",
        "The form now: " + json.dumps(form, ensure_ascii=False),
    ]
    if attachments:
        parts.append(attachments_line(attachments))
    parts.append("The administrator writes:\n" + text)
    return "\n".join(parts)


def messages(conversation: Conversation, current_turn: str) -> list[dict]:
    """The whole prompt: the system part, the conversation so far and this turn."""
    out = [{"role": "system", "content": system_prompt()}]
    for message in conversation.messages.all():
        if message.role == Message.Role.USER:
            content = message.text
            if message.attachments:
                content = f"{content}\n{attachments_line(message.attachments)}"
            out.append({"role": "user", "content": content})
        else:
            answer = {"reply": message.text, "set": message.fields}
            out.append({"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)})
    out.append({"role": "user", "content": current_turn})
    return out
