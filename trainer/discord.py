"""A Discord room for a virtual ride or race: a voice channel the site's bot opens on the club's server, and its
invitation.

Its host ticks "Create a Discord room" beside "Gather" on the virtual ride page; the site opens a voice channel named
after the route and the start, under the category ``DISCORD_CATEGORY_ID`` names where one is set, and makes an
invitation that never runs out (``GroupRide.discord_channel_id``, ``discord_invite_url``). The race's card shows it,
and an event made from the race carries it in its text, as it carries the race's link. A failure keeps the race and
says why. Every call goes through ``requests``, which the tests patch -- they never reach Discord.

A room lasts the day of the start and the whole day after it, in the zone of the race's event where it has one, else
UTC; a cancelled race's goes at once. ``close_due_rooms``, which the nightly cron asks for
(scripts/close_discord_rooms.py), deletes the channel and takes the invitation out of the event's text. Discord keeps
500 channels on a server, 50 in a category, so only the rooms of races to come take them.
"""

import datetime
import logging
import re
import time
from http import HTTPStatus

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.debug import sensitive_variables

from calendar_app.models import Competition
from locations.models import timezone_of

from .models import GroupRide

API = "https://discord.com/api/v10"
INVITE_BASE = "https://discord.gg/"
VOICE_CHANNEL = 2  # Discord's type of a voice channel
CHANNEL_NAME_MAX = 100  # Discord's longest channel name
# Discord's codes for a server or a category with no room for another channel (500 on a server, 50 in a category)
_NO_ROOM_CODES = ("30013", "CHANNEL_PARENT_MAX_CHANNELS")
# Gathering a race waits for Discord on one of the site's request threads: a slow Discord fails the room rather
# than hold the thread
_TIMEOUT = 10
# the line a room's invitation takes in an event's text (group-ride.js writes it): taken out once the room is gone,
# and only its own room's -- a link of the organizer's to another server stays
_ROOM_LINE = '<p>[^<]*<a href="{url}"[^>]*>[^<]*</a></p>'

logger = logging.getLogger(__name__)
# the day after the start is the room's too: it closes once that day is over
_DAYS_KEPT = 1
# rooms closed in one call, the oldest first, and the seconds it starts closing one more in: each waits for Discord
# up to _TIMEOUT on one of the site's request threads, which the server stops at 30 s, and the rest are closed the
# next night
CLOSE_PER_CALL = 20
CLOSE_SECONDS = 15


class DiscordError(Exception):
    pass


def configured() -> bool:
    """The site has a bot and a server to open rooms on."""
    return bool(settings.DISCORD_BOT_TOKEN and settings.DISCORD_GUILD_ID)


@sensitive_variables()  # the bot's token travels down through the HTTP library as its Authorization header
def _post(path: str, body: dict) -> dict:
    try:
        response = requests.post(
            f"{API}{path}",
            json=body,
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DiscordError(type(exc).__name__) from None
    if response.status_code not in (HTTPStatus.OK, HTTPStatus.CREATED):
        raise DiscordError(_refusal(response.status_code, response.text))
    try:
        return response.json()
    except ValueError:  # a proxy's page in place of Discord's answer
        raise DiscordError("Discord answered without JSON") from None


@sensitive_variables()
def _delete_channel(channel_id: str) -> None:
    """Delete a channel; one already gone is as good as deleted."""
    try:
        response = requests.delete(
            f"{API}/channels/{channel_id}",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DiscordError(type(exc).__name__) from None
    if response.status_code not in (HTTPStatus.OK, HTTPStatus.NO_CONTENT, HTTPStatus.NOT_FOUND):
        raise DiscordError(_refusal(response.status_code, response.text))


def _refusal(status: int, body: str = "") -> str:
    """Why Discord refused, in the words that say what to set up: the host passes them on to the admin."""
    if status == HTTPStatus.BAD_REQUEST and any(code in body for code in _NO_ROOM_CODES):
        return _("the server or its category has no room for another channel: 500 on a server, 50 in a category")
    if status == HTTPStatus.UNAUTHORIZED:
        return _("Discord does not accept the site's bot token")
    if status == HTTPStatus.FORBIDDEN:
        return _("the bot may not create channels or invitations on the server")
    if status == HTTPStatus.NOT_FOUND:
        return _("Discord does not know the server or the category the site names")
    return f"Discord answered {status}"


def _events(group: GroupRide):
    """The events the race is ridden in: the one it holds the timing of, and those made from it on the page."""
    return Competition.objects.filter(Q(virtual_races=group) | Q(virtual_ride=group.pk)).distinct()


def zone_of(group: GroupRide, default=None):
    """The zone of the race's event's place; else ``default``, else UTC -- the zone its days are counted in."""
    event = _events(group).select_related("location").first()
    return event.timezone if event is not None else default or timezone_of(None)


def _channel_name(group: GroupRide, zone) -> str:
    """The route and the start, as a rider looks for the room: "2026-12-01 18:00 Central loop"."""
    start = timezone.localtime(group.start_at, zone)
    return f"{start:%Y-%m-%d %H:%M} {group.route_name or group.route}"[:CHANNEL_NAME_MAX]


def open_room(group: GroupRide) -> str:
    """Open the race's Discord room; "" when it is open, else why there is none."""
    if group.discord_invite_url:
        return ""
    if not configured():
        return _("Discord is not set up on this site yet: ask its admin.")
    try:
        if not group.discord_channel_id:
            channel = _post(
                f"/guilds/{settings.DISCORD_GUILD_ID}/channels",
                {
                    # its start on its event's clock, else on its host's: the page they gather it on sends their zone
                    "name": _channel_name(group, zone_of(group, timezone.get_current_timezone())),
                    "type": VOICE_CHANNEL,
                    **({"parent_id": settings.DISCORD_CATEGORY_ID} if settings.DISCORD_CATEGORY_ID else {}),
                },
            )
            group.discord_channel_id = str(channel["id"])
            # kept at once: a channel whose invitation fails is still the race's, closed with it
            GroupRide.objects.filter(pk=group.pk).update(discord_channel_id=group.discord_channel_id)
        # an invitation that never runs out and takes any number of people
        invite = _post(f"/channels/{group.discord_channel_id}/invites", {"max_age": 0, "max_uses": 0, "unique": False})
        group.discord_invite_url = f"{INVITE_BASE}{invite['code']}"
    except (DiscordError, KeyError) as exc:
        return _("The Discord room could not be opened (%(reason)s).") % {"reason": exc}
    GroupRide.objects.filter(pk=group.pk).update(discord_invite_url=group.discord_invite_url)
    return ""


def is_over(group: GroupRide) -> bool:
    """The race is cancelled, or its start's day and the day after are over: its room is closed."""
    if group.cancelled:
        return True
    zone = zone_of(group)
    started = timezone.localtime(group.start_at, zone).date()
    return timezone.localdate(timezone=zone) > started + datetime.timedelta(days=_DAYS_KEPT)


def _take_out_of_texts(group: GroupRide) -> None:
    """The room's line out of the texts of the race's events."""
    line = re.compile(_ROOM_LINE.format(url=re.escape(group.discord_invite_url)))
    for event in _events(group):
        texts = {
            f"description_{lang}": line.sub("", getattr(event, f"description_{lang}") or "").strip()
            for lang in ("ru", "kk", "en")
        }
        # an update, not a save: the event's own fields and its review are not the room's to touch
        Competition.objects.filter(pk=event.pk).update(**texts)


def close_due_rooms() -> int:
    """Delete the rooms of the races that are over, take their invitations out of the events' texts; how many closed.

    A room Discord fails to delete, or one past ``CLOSE_PER_CALL`` or ``CLOSE_SECONDS``, is left for the next night.
    """
    if not settings.DISCORD_BOT_TOKEN:
        return 0
    # a superset: a start a day ago at least, whatever its zone, or a cancelled race -- narrowed by is_over
    latest = timezone.now() - datetime.timedelta(days=_DAYS_KEPT)
    due = (
        GroupRide.objects.exclude(discord_channel_id="")
        .filter(Q(cancelled=True) | Q(start_at__lte=latest))
        .order_by("start_at", "pk")[:CLOSE_PER_CALL]
    )
    closed, started = 0, time.monotonic()
    for group in due:
        if time.monotonic() - started > CLOSE_SECONDS:
            break
        if not is_over(group):
            continue
        try:
            _delete_channel(group.discord_channel_id)
        except DiscordError as exc:
            logger.warning("Discord room of race %s not closed: %s", group.pk, exc)
            continue
        if group.discord_invite_url:
            _take_out_of_texts(group)
        GroupRide.objects.filter(pk=group.pk).update(discord_channel_id="", discord_invite_url="")
        closed += 1
    return closed
