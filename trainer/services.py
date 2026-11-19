"""Where a member's rides go: Strava and intervals.icu, each connected or not, each with its box (#471).

One home for what the profile card, the trainer page and the API all ask: which services the site
offers, which the member connected, whether their box "send my rides there" is on, and the sending of a
freshly saved ride. The services' own round trips live in ``trainer.strava`` and ``trainer.intervals``.
"""

from . import intervals, strava
from .models import IntervalsConnection, IntervalsUpload, RideTrack, StravaConnection, StravaUpload, VirtualRide

STRAVA = "strava"
INTERVALS = "intervals"
SERVICES = (STRAVA, INTERVALS)


def _connection(user, service: str) -> StravaConnection | IntervalsConnection | None:
    model = StravaConnection if service == STRAVA else IntervalsConnection
    return model.objects.filter(user=user).first()


def state(user) -> dict:
    """Each service as the member sees it: offered, connected, the athlete there, the box."""
    out = {}
    for service, offered in ((STRAVA, strava.available()), (INTERVALS, intervals.available())):
        connection = _connection(user, service) if offered else None
        out[service] = {
            "available": offered,
            "connected": connection is not None,
            "athlete": connection.athlete_name if connection else "",
            "send_rides": bool(connection and connection.send_rides),
        }
    return out


def set_sending(user, service: str, on: bool) -> bool:
    """Turn the member's box for ``service`` on or off; False when that service is not connected."""
    connection = _connection(user, service)
    if connection is None:
        return False
    connection.send_rides = on
    connection.save(update_fields=["send_rides"])
    return True


def sendable(ride: VirtualRide) -> bool:
    """A ride a service can take: one with its track, not ridden on demo power."""
    return ride.power_source != VirtualRide.PowerSource.DEMO and RideTrack.objects.filter(ride=ride).exists()


def send_saved(ride: VirtualRide) -> tuple[StravaUpload | None, IntervalsUpload | None]:
    """A ride just saved goes to every service the member connected with its box on."""
    if not sendable(ride):
        return None, None
    sent = state(ride.user)
    to_strava = strava.upload(ride) if sent[STRAVA]["send_rides"] else None
    to_intervals = intervals.upload(ride) if sent[INTERVALS]["send_rides"] else None
    return to_strava, to_intervals
