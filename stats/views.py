"""The owners' statistics page (issue #184): who came, from where, what they read, what the robots and
the team did, and what happened on the site -- for a period, the same numbers as GET /api/v1/stats/ --
and what the server has left right now."""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.template.defaultfilters import filesizeformat
from django.utils import dateformat
from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from accounts import roles
from cycling_site import system
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


def _processors(value: float) -> str:
    """A number of processors as the language writes it, with no trailing zeros: 0.5, 1, 0.25."""
    return number_format(Decimal(f"{value:g}"))


def _server(resources: dict) -> list[dict]:
    """A tile per resource: how full it is and what of what; a dash where the system does not say."""
    disk, memory, cpu = resources["disk"], resources["memory"], resources["cpu"]
    tiles = (
        (_("Disk space used"), disk["percent"], disk["used"], disk["total"], filesizeformat, ""),
        (_("Memory used"), memory["percent"], memory["used"], memory["limit"], filesizeformat, ""),
        (_("Processor load"), cpu["percent"], cpu["used"], cpu["limit"], _processors, " CPU"),
    )
    return [
        {"name": name, "percent": percent, "detail": "" if percent is None else f"{shown(used)} / {shown(whole)}{unit}"}
        for name, percent, used, whole, shown, unit in tiles
    ]


@login_required
def dashboard(request):
    if not roles.at_least(request.user, roles.SEE_SITE_STATS):
        raise PermissionDenied
    data = report.build(request.GET.get("period", report.DEFAULT_PERIOD))
    people, bots, bucket = data["people"], data["bots"], data["bucket"]
    resources = system.read()
    return render(
        request,
        "stats/dashboard.html",
        {
            "data": data,
            "periods": [(period, PERIOD_NAMES[period]) for period in report.PERIODS],
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
            "server": _server(resources),
            "database_mb": None if resources["database"]["size"] is None else resources["database"]["size"] / 2**20,
            "meta_title": _("Statistics"),
        },
    )
