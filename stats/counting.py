"""Adding one to the day's tallies (issue #184): robots and the team as their pages go out
(stats.middleware), people when their browser says it opened a page (api.endpoints.stats)."""

import datetime
from urllib.parse import urlsplit

from django.db import connection
from django.utils import timezone, translation

from accounts import roles
from stats.models import KEY_LENGTH, Tally
from stats.robots import is_phone

#: The dimensions whose keys come from the request -- a page's path, the site a visit came from, a
#: robot's name -- so a script could name endless ones. A day takes up to DAILY_KEYS of each; past
#: that a new key goes uncounted there, while the day's totals still count it.
OPEN_ENDED = (Tally.Dimension.PAGE, Tally.Dimension.SOURCE, Tally.Dimension.BOT)
DAILY_KEYS = 500


def now() -> datetime.datetime:
    """This moment in the site's own time zone: a reader's zone, which a page may switch to, would move
    the day's boundary from one reader to the next."""
    return timezone.localtime(timezone=timezone.get_default_timezone())


def add(*pairs: tuple[str, str]) -> None:
    """One more for each ``(dimension, key)`` today; a row is made the first time.

    One write whatever the number of pairs, and safe when two requests count the same row at once.
    """
    day = now().date()
    rows = [(day, dimension, key[:KEY_LENGTH]) for dimension, key in dict.fromkeys(pairs)]
    rows = [row for row in rows if row[1] not in OPEN_ENDED or _room_for(*row)]
    if not rows:
        return
    table = Tally._meta.db_table
    values = ", ".join(["(%s, %s, %s, 1)"] * len(rows))
    with connection.cursor() as cursor:
        cursor.execute(
            # The table's name is the model's own, never a value from a request: those go as parameters.
            f"INSERT INTO {table} (day, dimension, key, count) VALUES {values} "  # noqa: S608
            f"ON CONFLICT (day, dimension, key) DO UPDATE SET count = {table}.count + 1",
            [value for row in rows for value in row],
        )


def _room_for(day: datetime.date, dimension: str, key: str) -> bool:
    """Whether the day's tallies of ``dimension`` take ``key``: one they have, or a new one below DAILY_KEYS."""
    tallies = Tally.objects.filter(day=day, dimension=dimension)
    return tallies.filter(key=key).exists() or tallies.count() < DAILY_KEYS


def is_team(user) -> bool:
    """The people who run the site: their pages are their work, counted apart from readers'."""
    return roles.at_least(user, roles.COUNTED_AS_TEAM)


def _source(referrer: str, own_host: str) -> str | None:
    """The site a visit came from, DIRECT when none; None for a page of our own -- not a new visit."""
    host = (urlsplit(referrer).hostname or "").lower() if referrer else ""
    if not host:
        return Tally.DIRECT
    if host == own_host or host.endswith(f".{own_host}"):
        return None
    return host.removeprefix("www.")


def count_person(path: str, referrer: str, user_agent: str, own_host: str) -> None:
    """A person opened ``path``: a view, in its hour and its language, and a visit when they came from
    outside the site -- where from, on a phone or a computer. Only pages in a language count."""
    language = translation.get_language_from_path(path)
    if not language or not path.startswith(f"/{language}/"):
        return
    pairs = [
        (Tally.Dimension.VIEWS, Tally.Audience.PEOPLE),
        (Tally.Dimension.HOUR, now().strftime("%H")),
        (Tally.Dimension.PAGE, path),
        (Tally.Dimension.LANGUAGE, language),
    ]
    source = _source(referrer, own_host.split(":", 1)[0])
    if source is not None:
        device = Tally.Device.PHONE if is_phone(user_agent) else Tally.Device.COMPUTER
        pairs += [
            (Tally.Dimension.VISITS, Tally.Audience.PEOPLE),
            (Tally.Dimension.SOURCE, source),
            (Tally.Dimension.DEVICE, device),
        ]
    add(*pairs)
