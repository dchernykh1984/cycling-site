"""The slug an article without one gets from its title."""

from collections.abc import Callable

from django.utils.text import slugify


def unique_slug(title: str, max_length: int, taken: Callable[[str], bool]) -> str:
    """An ASCII slug of ``title`` at most ``max_length`` long, numbered on while ``taken`` says so.

    The number takes its room from the title's part, so even a title of the column's full length
    cannot push the slug past it: a 255-character title would otherwise give a 257-character
    "...-1" and a DataError on PostgreSQL.
    """
    base = (slugify(title or "") or "article")[:max_length]
    candidate = base
    n = 1
    while taken(candidate):
        suffix = f"-{n}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        n += 1
    return candidate
