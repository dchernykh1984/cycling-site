"""What the owners' statistics show for a period (issue #184): the tallies summed over it, and what the
site's own tables say happened in it. The page and the API both read ``build``."""

import datetime
import re
from collections import defaultdict

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts import roles
from accounts.adapters import user_display
from stats import counting
from stats.models import Tally

#: The periods, by the name the page and the API ask for them by.
PERIODS = ("today", "week", "month", "quarter", "ytd", "year", "all")
DEFAULT_PERIOD = "month"
#: How many lines a list of pages, sources or robots shows.
TOP = 20
_EVENT = re.compile(r"^/[a-z]{2}/calendar/(\d+)/$")
_ARTICLE = re.compile(r"^/[a-z]{2}/knowledge/([\w-]+)/$")


def _span(period: str, today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """The first and the last day of a period, both counted, ending today."""
    if period == "today":
        return today, today
    if period == "ytd":
        return today.replace(month=1, day=1), today
    if period == "all":
        first = Tally.objects.order_by("day").values_list("day", flat=True).first()
        return min(first or today, today), today
    days = {"week": 7, "month": 30, "quarter": 90, "year": 365}[period]
    return today - datetime.timedelta(days=days - 1), today


def _bucket(start: datetime.date, end: datetime.date) -> str:
    """How finely a period is drawn: hours for a day, days up to a quarter, weeks up to two years."""
    length = (end - start).days + 1
    if length == 1:
        return "hour"
    if length <= 92:
        return "day"
    return "week" if length <= 731 else "month"


def _bucket_of(day: datetime.date, bucket: str) -> datetime.date:
    if bucket == "week":
        return day - datetime.timedelta(days=day.weekday())
    if bucket == "month":
        return day.replace(day=1)
    return day


def _buckets(start: datetime.date, end: datetime.date, bucket: str) -> list[datetime.date]:
    """Every bucket of the period in order, empty ones too: a gap on a chart is a zero, not a jump."""
    found: list[datetime.date] = []
    day = start
    while day <= end:
        at = _bucket_of(day, bucket)
        if not found or found[-1] != at:
            found.append(at)
        day += datetime.timedelta(days=1)
    return found


def _sums(dimension: str, start, end, limit=None) -> list[tuple[str, int]]:
    rows = (
        Tally.objects.filter(dimension=dimension, day__range=(start, end))
        .values("key")
        .annotate(total=Sum("count"))
        .order_by("-total", "key")
    )
    return [(row["key"], row["total"]) for row in (rows[:limit] if limit else rows)]


def _by_day(dimension: str, keys, start, end) -> dict[tuple[datetime.date, str], int]:
    rows = Tally.objects.filter(dimension=dimension, key__in=keys, day__range=(start, end)).values_list(
        "day", "key", "count"
    )
    return {(day, key): count for day, key, count in rows}


def _moments(start: datetime.date, end: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """The period as two moments in the site's time zone: its first instant and the next day's."""
    zone = timezone.get_default_timezone()
    return (
        datetime.datetime.combine(start, datetime.time.min, zone),
        datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min, zone),
    )


def _titles(paths: list[str]) -> dict[str, str]:
    """An event's or an article's title for its page, so a list of addresses reads as a list of things."""
    from calendar_app.models import Competition
    from knowledge.models import KnowledgeArticle

    events = {path: int(m.group(1)) for path in paths if (m := _EVENT.match(path))}
    articles = {path: m.group(1) for path in paths if (m := _ARTICLE.match(path))}
    named = dict(Competition.objects.filter(pk__in=events.values()).values_list("pk", "title"))
    slugs = dict(KnowledgeArticle.objects.filter(slug__in=articles.values()).values_list("slug", "title"))
    titles = {path: named[pk] for path, pk in events.items() if pk in named}
    titles.update({path: slugs[slug] for path, slug in articles.items() if slug in slugs})
    return titles


def _people(start, end, bucket, at_hours) -> dict:
    views = dict(_sums(Tally.Dimension.VIEWS, start, end)).get(Tally.Audience.PEOPLE, 0)
    visits = dict(_sums(Tally.Dimension.VISITS, start, end)).get(Tally.Audience.PEOPLE, 0)
    if at_hours:
        hours = dict(_sums(Tally.Dimension.HOUR, start, end))
        series = [{"at": f"{hour:02d}:00", "views": hours.get(f"{hour:02d}", 0)} for hour in range(24)]
    else:
        daily = _by_day(Tally.Dimension.VIEWS, [Tally.Audience.PEOPLE], start, end)
        entries = _by_day(Tally.Dimension.VISITS, [Tally.Audience.PEOPLE], start, end)
        totals: dict[datetime.date, dict[str, int]] = defaultdict(lambda: {"views": 0, "visits": 0})
        for (day, _key), count in daily.items():
            totals[_bucket_of(day, bucket)]["views"] += count
        for (day, _key), count in entries.items():
            totals[_bucket_of(day, bucket)]["visits"] += count
        series = [{"at": at, **totals[at]} for at in _buckets(start, end, bucket)]
    pages = _sums(Tally.Dimension.PAGE, start, end, TOP)
    titles = _titles([path for path, _ in pages])
    return {
        "views": views,
        "visits": visits,
        "views_per_visit": round(views / visits, 1) if visits else None,
        "series": series,
        "pages": [{"path": path, "title": titles.get(path, ""), "views": n} for path, n in pages],
        "sources": [{"name": name, "visits": n} for name, n in _sums(Tally.Dimension.SOURCE, start, end, TOP)],
        "devices": [{"name": name, "visits": n} for name, n in _sums(Tally.Dimension.DEVICE, start, end)],
        "languages": [{"name": name, "views": n} for name, n in _sums(Tally.Dimension.LANGUAGE, start, end)],
    }


def _bots(start, end, bucket) -> dict:
    names = _sums(Tally.Dimension.BOT, start, end)
    kinds: dict[str, int] = defaultdict(int)
    for key, n in names:
        kinds[key.split(":", 1)[0]] += n
    daily = _by_day(Tally.Dimension.VIEWS, [Tally.Audience.BOTS], start, end)
    totals: dict[datetime.date, int] = defaultdict(int)
    for (day, _key), count in daily.items():
        totals[_bucket_of(day, bucket)] += count
    return {
        # The day's total, not the names': past a day's limit of names a robot goes unnamed, still counted.
        "views": dict(_sums(Tally.Dimension.VIEWS, start, end)).get(Tally.Audience.BOTS, 0),
        "series": [{"at": at, "views": totals[at]} for at in _buckets(start, end, bucket)],
        "kinds": [{"kind": kind, "views": n} for kind, n in sorted(kinds.items(), key=lambda item: -item[1])],
        "names": [{"kind": key.split(":", 1)[0], "name": key.split(":", 1)[-1], "views": n} for key, n in names[:TOP]],
    }


def _team(start, end, bucket) -> dict:
    """The owners' and admins' own pages and the changes they made (the audit log), member by member."""
    from accounts.models import User
    from audit.models import AuditLog

    first, after = _moments(start, end)
    team = {user.pk: user for user in User.objects.filter(roles.holding(roles.COUNTED_AS_TEAM))}
    views = {int(key): n for key, n in _sums(Tally.Dimension.TEAM, start, end) if key.isdecimal()}
    changes = AuditLog.objects.filter(user_id__in=team, timestamp__gte=first, timestamp__lt=after)
    actions = dict(changes.values("user_id").annotate(n=Count("pk")).values_list("user_id", "n"))
    by_day: dict[datetime.date, dict[str, int]] = defaultdict(lambda: {"views": 0, "actions": 0})
    for (day, _key), count in _by_day(Tally.Dimension.VIEWS, [Tally.Audience.TEAM], start, end).items():
        by_day[_bucket_of(day, bucket)]["views"] += count
    for day, n in (
        changes.annotate(day=TruncDate("timestamp", tzinfo=timezone.get_default_timezone()))
        .values("day")
        .annotate(n=Count("pk"))
        .values_list("day", "n")
    ):
        by_day[_bucket_of(day, bucket)]["actions"] += n
    members = [
        {"name": user_display(user), "views": views.get(pk, 0), "actions": actions.get(pk, 0)}
        for pk, user in team.items()
    ]
    return {
        "views": sum(views.values()),
        "actions": sum(actions.values()),
        "series": [{"at": at, **by_day[at]} for at in _buckets(start, end, bucket)],
        "members": sorted(members, key=lambda row: (-row["views"] - row["actions"], row["name"])),
    }


def _site(start, end) -> dict:
    """What the site's own tables say happened in the period: who joined, what was added and done."""
    from accounts.models import User
    from calendar_app.models import Competition, CompetitionStatusChange
    from registrations.models import CompetitionRegistration
    from trainer.models import StravaConnection, VirtualRide

    first, after = _moments(start, end)
    joined = User.objects.filter(is_active=True, date_joined__gte=first, date_joined__lt=after).order_by("-date_joined")
    changes = CompetitionStatusChange.objects.filter(changed_at__gte=first, changed_at__lt=after)
    return {
        "members": User.objects.filter(is_active=True).count(),
        "new_members": joined.count(),
        "signed_in": User.objects.filter(last_login__gte=first, last_login__lt=after).count(),
        "strava": StravaConnection.objects.count(),
        "new_strava": StravaConnection.objects.filter(connected_at__gte=first, connected_at__lt=after).count(),
        "events_added": changes.filter(added=True).count(),
        "events_approved": changes.filter(status=Competition.Status.APPROVED)
        .filter(~Q(previous_status=Competition.Status.APPROVED))
        .count(),
        "events_pending": Competition.objects.filter(
            status=Competition.Status.PENDING_APPROVAL, is_deleted=False
        ).count(),
        "registrations": CompetitionRegistration.objects.filter(
            registered_at__gte=first, registered_at__lt=after
        ).count(),
        "rides": VirtualRide.objects.filter(finished_at__gte=first, finished_at__lt=after).count(),
        "newcomers": [{"name": user_display(user), "joined": user.date_joined} for user in joined[:TOP]],
    }


def build(period: str) -> dict:
    """Everything the page and the API show for a period of PERIODS (an unknown one reads as the default).

    Days are dates and moments are datetimes, for the page to write in its reader's words and the API
    in ISO 8601; a point of a chart is the first day of its bucket, or "HH:00" for an hour of a day.
    """
    period = period if period in PERIODS else DEFAULT_PERIOD
    start, end = _span(period, counting.now().date())
    bucket = _bucket(start, end)
    return {
        "period": period,
        "start": start,
        "end": end,
        "bucket": bucket,
        "people": _people(start, end, bucket, at_hours=bucket == "hour"),
        "bots": _bots(start, end, bucket),
        "team": _team(start, end, bucket),
        "site": _site(start, end),
    }
