"""The model's answer, checked into the event form's values (issue #353).

The answer is input like any other (constitution X): each value is checked against its field, and
only what passes reaches the page. A link must appear in the administrator's own messages and a
place must be one of the site's (constitution I). What is left out becomes a note the chat shows, so
that a reply never claims what the form does not hold.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext as _

from assistant import places
from assistant.prompt import LANGUAGES, TEXT_FIELDS, URL_FIELDS
from calendar_app.models import Competition, Discipline, EventType
from cycling_site.sanitize import sanitize_rich_html

_MAX = {
    "title": 255,
    "preview_text": Competition._meta.get_field("preview_text").max_length,
    "description": 1_000_000,  # the editor's own bound
}
_URL_MAX = Competition._meta.get_field("url_route").max_length or 200
_SCHEME = re.compile(r"^(?:https?://)?(?:www\.)?", re.IGNORECASE)


@dataclass
class Checked:
    """What a reply may do: ``set`` is kept, in the contract's words; ``form`` goes to the page."""

    set: dict = field(default_factory=dict)
    form: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _bare(url: str) -> str:
    return _SCHEME.sub("", url.strip()).rstrip("/").lower()


def written_by_them(url: str, texts: list[str]) -> bool:
    """Whether one of ``texts`` holds this link, give or take its scheme, "www." and a final slash."""
    bare = _bare(url)
    return bool(bare) and any(bare in text.lower() for text in texts)


def _line(value) -> str:
    return value.strip()[:255] if isinstance(value, str) else ""


def _url(value: str) -> str | None:
    url = value.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError:
        return None
    return url if len(url) <= _URL_MAX else None


def _typed_point(place: dict, texts: list[str]) -> places.Point | None:
    """The coordinates the model gave, when the administrator wrote both numbers."""
    try:
        lat, lng = float(place["lat"]), float(place["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    joined = " ".join(texts).replace(",", ".")
    written = all(re.search(rf"(?<![\d.]){re.escape(str(number))}", joined) for number in (place["lat"], place["lng"]))
    return (lat, lng) if written else None


class _Checker:
    def __init__(self, current: dict, texts: list[str], rows: list[dict], point: places.Point | None):
        self.current = current
        self.texts = texts
        # A link may also come from the form as it stands: an edited event's own links, and the ones
        # its descriptions carry, were written by people too.
        descriptions = current.get("description")
        written = list(descriptions.values()) if isinstance(descriptions, dict) else []
        self.sources = [*texts, *(str(current.get(name) or "") for name in URL_FIELDS), *map(str, written)]
        self.rows = rows
        self.point = point
        self.out = Checked()

    def texts_in_three_languages(self, answer: dict) -> None:
        for name in TEXT_FIELDS:
            value = answer.get(name)
            if not isinstance(value, dict):
                continue
            kept = {}
            for lang in LANGUAGES:
                text = value.get(lang)
                if not isinstance(text, str):
                    continue
                text = text.strip()
                if name == "description":
                    text = sanitize_rich_html(text)
                kept[lang] = text[: _MAX[name]]
                self.out.form[f"{name}_{lang}"] = kept[lang]
            if kept:
                self.out.set[name] = kept

    def dates(self, answer: dict) -> None:
        for name in ("date_start", "date_end"):
            if name not in answer:
                continue
            value = answer[name]
            if value in ("", None):
                self.out.set[name] = self.out.form[name] = ""
                continue
            try:
                self.out.set[name] = self.out.form[name] = datetime.date.fromisoformat(str(value)).isoformat()
            except ValueError:
                continue
        # An end before the start -- the model's, or the form's own after the start moved -- is emptied.
        start = self.out.form.get("date_start", self.current.get("date_start", ""))
        end = self.out.form.get("date_end", self.current.get("date_end", ""))
        if start and end and end < start:
            self.out.set["date_end"] = self.out.form["date_end"] = ""

    def ids(self, answer: dict) -> None:
        for name, form_name, model in (
            ("event_type_ids", "event_types", EventType),
            ("discipline_ids", "disciplines", Discipline),
        ):
            value = answer.get(name)
            if not isinstance(value, list):
                continue
            asked = [int(item) for item in value if str(item).isdigit()]
            known = set(model.objects.filter(pk__in=asked).values_list("pk", flat=True))
            self.out.set[name] = self.out.form[form_name] = [pk for pk in asked if pk in known]

    def links(self, answer: dict) -> None:
        for name in URL_FIELDS:
            value = answer.get(name)
            if not isinstance(value, str):
                continue
            if not value.strip():
                self.out.set[name] = self.out.form[name] = ""
                continue
            url = _url(value)
            if url is None or not written_by_them(value, self.sources):
                self.out.notes.append(
                    _("A link that is in neither your messages nor the form was left out: %(url)s") % {"url": value}
                )
                continue
            self.out.set[name] = self.out.form[name] = url

    def place(self, answer: dict) -> None:
        given = answer.get("place")
        if not isinstance(given, dict):
            return
        venue = given.get("venue")
        venue = venue if isinstance(venue, dict) else {}
        place = {
            **{key: _line(given.get(key)) for key in ("country", "region", "city")},
            "venue": {lang: _line(venue.get(lang)) for lang in LANGUAGES},
            "lat": given.get("lat") if isinstance(given.get("lat"), (int, float, str)) else None,
            "lng": given.get("lng") if isinstance(given.get("lng"), (int, float, str)) else None,
        }
        found = places.resolve(place, self.rows, _typed_point(place, self.texts) or self.point)
        if found.location is not None:
            self.out.form["location"] = found.location
        elif found.new_venue is not None:
            self.out.form["new_venue"] = found.new_venue
        else:
            if found.missing_city:
                self.out.notes.append(
                    _("%(city)s is not among the site's places: choose the place in the form.")
                    % {"city": found.missing_city}
                )
            return
        self.out.set["place"] = place


def check(
    answer: dict, *, current: dict, texts: list[str], rows: list[dict], point: places.Point | None = None
) -> Checked:
    """The parts of the model's ``set`` that pass, as kept and as the page's form values, with notes.

    ``current`` is the form as it stands (``prompt.describe_form``), ``texts`` everything the
    administrator wrote in the conversation, ``rows`` the places the page offers, and ``point`` the
    start of a track they attached.
    """
    checker = _Checker(current, texts, rows, point)
    if isinstance(answer, dict):
        checker.texts_in_three_languages(answer)
        checker.dates(answer)
        checker.ids(answer)
        checker.links(answer)
        checker.place(answer)
    return checker.out
