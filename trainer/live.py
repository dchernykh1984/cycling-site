"""Riding together: who is on the trainer page now, open group races, and the riders next to you.

The page polls the site about once a second while riding and every few seconds while setting up,
sending its own state and getting the others back. Nothing here needs a socket server or a shared
cache: the rows live in the database and go stale on their own.
"""

from datetime import timedelta

from django.utils import timezone

from .models import GroupRide, LiveRider, VirtualRide, VoiceSession

# A row not refreshed for this long belongs to someone who closed the page.
ONLINE_SECONDS = 15
# A group race stays listed this long after its start, so late polls still find it.
GROUP_LISTED_AFTER_START = timedelta(minutes=5)
MIN_START_DELAY_S = 20
MAX_START_DELAY_S = 3600


def online(now=None):
    """Who is on the page, in a steady order: each poll rewrites a row, and an unordered list reshuffles."""
    now = now or timezone.now()
    recent = LiveRider.objects.filter(updated_at__gte=now - timedelta(seconds=ONLINE_SECONDS))
    return recent.select_related("user").order_by("user_id")


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


def in_voice(group: GroupRide, now=None):
    """Who is in a race's voice chat now: someone whose page stopped polling is not."""
    now = now or timezone.now()
    since = now - timedelta(seconds=ONLINE_SECONDS)
    return (
        VoiceSession.objects.filter(group=group, user__live_ride__updated_at__gte=since)
        .select_related("user")
        .order_by("user_id")
    )


def voice_room(user, me_row: LiveRider, now=None):
    """The voice chat a rider belongs to and who else is in it.

    Their own chat once they joined one; before that the race they ride or wait for, so the page can say
    who is talking there.
    """
    now = now or timezone.now()
    mine = VoiceSession.objects.filter(user=user).select_related("group").first()
    waiting = GroupRide.objects.filter(
        cancelled=False, start_at__gte=now - GROUP_LISTED_AFTER_START, memberships__user=user
    ).order_by("start_at")
    group = mine.group if mine else me_row.group or waiting.first()
    if group is None:
        return None, VoiceSession.objects.none()
    return group, in_voice(group, now).exclude(user=user)
