"""Riding together: who is on the trainer page now, open group races, and the riders next to you.

The page polls the site about once a second while riding and every few seconds while setting up,
sending its own state and getting the others back. Nothing here needs a socket server or a shared
cache: the rows live in the database and go stale on their own.
"""

from datetime import timedelta

from django.utils import timezone

from .models import GroupRide, LiveRider, VirtualRide

# A row not refreshed for this long belongs to someone who closed the page.
ONLINE_SECONDS = 15
# A group race stays listed this long after its start, so late polls still find it.
GROUP_LISTED_AFTER_START = timedelta(minutes=5)
MIN_START_DELAY_S = 20
MAX_START_DELAY_S = 3600


def online(now=None):
    now = now or timezone.now()
    return LiveRider.objects.filter(updated_at__gte=now - timedelta(seconds=ONLINE_SECONDS)).select_related("user")


def open_groups(now=None):
    """Group races that have not started yet, or started only moments ago."""
    now = now or timezone.now()
    return (
        GroupRide.objects.filter(cancelled=False, start_at__gte=now - GROUP_LISTED_AFTER_START)
        .select_related("host")
        .prefetch_related("memberships__user")
        .order_by("start_at")
    )


def riders_beside(me: LiveRider, now=None):
    """The others a rider should see on the road: their group race, or free riders on the same route."""
    if me.status != LiveRider.Status.RIDE or not me.route:
        return LiveRider.objects.none()
    others = online(now).filter(status=LiveRider.Status.RIDE, route=me.route).exclude(user=me.user)
    if me.group_id:
        return others.filter(group_id=me.group_id)
    if me.mode == VirtualRide.Kind.FREE:
        return others.filter(group__isnull=True, mode=VirtualRide.Kind.FREE)
    return LiveRider.objects.none()
