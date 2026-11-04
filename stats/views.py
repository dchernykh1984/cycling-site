"""The owners' statistics page (issue #184): who came, from where, what they read, what the robots and
the team did, and what happened on the site -- for a period, the same numbers as GET /api/v1/stats/."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import dateformat
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from accounts import roles
from stats import report
from stats.models import Tally

PERIOD_NAMES = {
    "today": gettext_lazy("Today"),
    "week": gettext_lazy("Week"),
    "month": gettext_lazy("30 days"),
    "quarter": gettext_lazy("90 days"),
    "ytd": gettext_lazy("Since the start of the year"),
    "year": gettext_lazy("Year"),
    "all": gettext_lazy("All time"),
}
KIND_NAMES = {
    "assistant": gettext_lazy("AI assistants opening a page for a person"),
    "ai_search": gettext_lazy("AI search"),
    "search": gettext_lazy("Search engines"),
    "ai_training": gettext_lazy("AI training"),
    "preview": gettext_lazy("Link previews in messengers"),
    "seo": gettext_lazy("Marketing services (SEO)"),
    "monitor": gettext_lazy("Monitoring and scripts"),
    "own": gettext_lazy("Our own scripts"),
    "other": gettext_lazy("Other robots"),
}
POINT_FORMATS = {"day": "d.m", "week": "d.m.Y", "month": "m.Y"}
DEVICE_NAMES = {Tally.Device.PHONE: gettext_lazy("Phone"), Tally.Device.COMPUTER: gettext_lazy("Computer")}


def _ranked(rows, value, name=lambda row: row["name"]):
    """Rows for a list of bars, each with its share of the longest bar."""
    top = max((row[value] for row in rows), default=0)
    return [
        {"name": name(row), "value": row[value], "width": round(row[value] * 100 / top) if top else 0} for row in rows
    ]


def _chart(series: list[dict], lines: list[tuple[str, str]], bucket: str) -> dict:
    """A chart's lines -- those its points have -- and its points with their time as the page writes it."""
    lines = [(key, name) for key, name in lines if series and key in series[0]]
    return {
        "names": [name for _key, name in lines],
        "points": [
            {
                # The period's own dates stand above the chart: a day needs no year there.
                "at": row["at"] if bucket == "hour" else dateformat.format(row["at"], POINT_FORMATS[bucket]),
                "values": [row[key] for key, _name in lines],
            }
            for row in series
        ],
    }


@login_required
def dashboard(request):
    if not roles.at_least(request.user, roles.SEE_SITE_STATS):
        raise PermissionDenied
    data = report.build(request.GET.get("period", report.DEFAULT_PERIOD))
    people, bots, bucket = data["people"], data["bots"], data["bucket"]
    return render(
        request,
        "stats/dashboard.html",
        {
            "data": data,
            "periods": PERIOD_NAMES.items(),
            "sources": _ranked(
                people["sources"],
                "visits",
                lambda row: _("Direct, with no link") if row["name"] == Tally.DIRECT else row["name"],
            ),
            "devices": _ranked(people["devices"], "visits", lambda row: DEVICE_NAMES.get(row["name"], row["name"])),
            "languages": _ranked(people["languages"], "views", lambda row: row["name"].upper()),
            "kinds": _ranked(bots["kinds"], "views", lambda row: KIND_NAMES.get(row["kind"], row["kind"])),
            "robots": [{**row, "kind_name": KIND_NAMES.get(row["kind"], row["kind"])} for row in bots["names"]],
            "charts": {
                "people": _chart(people["series"], [("visits", _("Visits")), ("views", _("Page views"))], bucket),
                "bots": _chart(bots["series"], [("views", _("Page views"))], bucket),
                "team": _chart(
                    data["team"]["series"], [("views", _("Pages opened")), ("actions", _("Changes made"))], bucket
                ),
            },
            "meta_title": _("Statistics"),
        },
    )
