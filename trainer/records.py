"""Personal records derived from a member's saved virtual rides.

Records are computed from the rides rather than stored, so deleting a ride can never leave a stale
record behind. Rides in demo mode (power set by hand) are kept in the history but never count.
"""

from dataclasses import dataclass

from django.db.models import Count, Max, Min, Sum

from . import strava
from .models import StravaConnection, VirtualRide

PEAK_FIELDS = ("peak_5s_w", "peak_1m_w", "peak_5m_w", "peak_20m_w")


def counted(user):
    """The rides that may set a record: the member's own, not in demo mode."""
    return VirtualRide.objects.filter(user=user).exclude(power_source=VirtualRide.PowerSource.DEMO)


@dataclass
class RouteBest:
    route: str
    route_name: str
    duration_s: float
    finished_at: object
    attempts: int
    best_avg_power_w: int | None


def route_bests(user) -> list[RouteBest]:
    """The fastest race on each route the member has raced, with how many times they raced it."""
    races = counted(user).filter(kind=VirtualRide.Kind.RACE)
    stats = {
        row["route"]: row for row in races.values("route").annotate(attempts=Count("id"), best_power=Max("avg_power_w"))
    }
    bests: dict[str, VirtualRide] = {}
    for ride in races.order_by("route", "duration_s", "finished_at"):
        bests.setdefault(ride.route, ride)
    return [
        RouteBest(
            route=route,
            route_name=ride.route_name or route,
            duration_s=ride.duration_s,
            finished_at=ride.finished_at,
            attempts=stats[route]["attempts"],
            best_avg_power_w=stats[route]["best_power"],
        )
        for route, ride in sorted(bests.items(), key=lambda item: item[1].route_name or item[0])
    ]


def summary(user) -> dict:
    """Totals over every ride, record peaks and top speed over the counted ones."""
    rides = VirtualRide.objects.filter(user=user)
    totals = rides.aggregate(
        rides=Count("id"), distance_m=Sum("distance_m"), elevation_m=Sum("elevation_gain_m"), time_s=Sum("duration_s")
    )
    peaks = counted(user).aggregate(**{field: Max(field) for field in PEAK_FIELDS}, max_speed_kmh=Max("max_speed_kmh"))
    return {
        "rides": totals["rides"] or 0,
        "distance_km": round((totals["distance_m"] or 0) / 1000, 1),
        "elevation_m": round(totals["elevation_m"] or 0),
        "time_s": round(totals["time_s"] or 0),
        "max_speed_kmh": peaks.pop("max_speed_kmh"),
        "peaks": peaks,
        "routes": route_bests(user),
    }


def new_records(user, ride: VirtualRide) -> list[str]:
    """Which records ``ride`` sets, compared with the member's rides saved before it.

    Keys, not sentences: the trainer page words them in its own language. ``route_first`` is the
    first counted race on a route, ``route_best`` a faster one; peaks and top speed only count once
    an earlier ride exists to beat, so a first ride does not announce a dozen \"records\".
    """
    if ride.power_source == VirtualRide.PowerSource.DEMO:
        return []
    before = counted(user).exclude(pk=ride.pk).filter(finished_at__lte=ride.finished_at)
    found = []
    if ride.kind == VirtualRide.Kind.RACE:
        best = before.filter(kind=VirtualRide.Kind.RACE, route=ride.route).aggregate(best=Min("duration_s"))["best"]
        if best is None:
            found.append("route_first")
        elif ride.duration_s < best:
            found.append("route_best")
    if not before.exists():
        return found
    previous = before.aggregate(**{field: Max(field) for field in PEAK_FIELDS}, max_speed=Max("max_speed_kmh"))
    for field in PEAK_FIELDS:
        value = getattr(ride, field)
        if value and value > (previous[field] or 0):
            found.append(field)
    if ride.max_speed_kmh > (previous["max_speed"] or 0):
        found.append("max_speed_kmh")
    return found


def rank_group(group) -> None:
    """Give every finished ride of a group race its place among the members, fastest first.

    Places come from the saved times, not from what each rider's page counted at its own finish line:
    a page that lost sight of the others for a moment would otherwise call itself the winner.
    """
    finishers = group_results(group)
    field = max(group.memberships.count(), len(finishers))
    for place, ride in enumerate(finishers, start=1):
        if (ride.place, ride.field_size) != (place, field):
            ride.place, ride.field_size = place, field
            ride.save(update_fields=["place", "field_size"])


def group_results(group) -> list[VirtualRide]:
    """The finished rides of a group race, fastest first; one per member (their first finish)."""
    first: dict[int, VirtualRide] = {}
    for ride in group.rides.filter(kind=VirtualRide.Kind.RACE).select_related("user").order_by("finished_at"):
        first.setdefault(ride.user_id, ride)
    return sorted(first.values(), key=lambda r: r.duration_s)


def duration_label(seconds: float) -> str:
    """A ride time as the trainer page shows it: m:ss, or h:mm:ss from an hour on."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def profile_context(user, recent: int = 5) -> dict:
    """What the profile's virtual ride card shows: the summary plus the latest rides, times labelled."""
    data = summary(user)
    for best in data["routes"]:
        best.time_label = duration_label(best.duration_s)  # type: ignore[attr-defined]
    data["time_label"] = duration_label(data["time_s"])
    data["recent"] = list(VirtualRide.objects.filter(user=user).select_related("strava")[:recent])
    for ride in data["recent"]:
        ride.time_label = duration_label(ride.duration_s)  # type: ignore[attr-defined]
        ride.distance_km = round(ride.distance_m / 1000, 1)  # type: ignore[attr-defined]
    # Sending rides to Strava: offered when the site has a Strava application, on once the member allows it
    data["strava_available"] = strava.available()
    data["strava"] = StravaConnection.objects.filter(user=user).first()
    return data
