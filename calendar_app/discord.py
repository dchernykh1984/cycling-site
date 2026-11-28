"""A Discord room for an event: a voice channel the site's bot opens on the club's server, and its invitation.

An organizer ticks the event form's box "Create a Discord room" (``Competition.discord_room``); once the event is
saved the site opens a voice channel named after it, under the category ``DISCORD_CATEGORY_ID`` names where one is
set, makes an invitation that never runs out and writes it into the event's text in each language. The room is
opened once: the channel and its invitation stay with the event (``discord_channel_id``, ``discord_invite_url``),
and unticking the box later leaves the room on Discord. A failure keeps the event and its box, and the next save
tries again. Every call goes through ``requests``, which the tests patch -- they never reach Discord.

A room lasts the event and the whole day after it at the event's place: ``close_due_rooms``, which the nightly
cron asks for (scripts/close_discord_rooms.py), deletes its channel from then on and takes the invitation out of
the event's text, and an event that is over opens no room. Discord keeps 500 channels on a server, 50 in a
category, so only the rooms of events to come take them.
"""

import datetime
import logging
import re
import time
from http import HTTPStatus

import requests
from django.conf import settings
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import override
from django.views.decorators.debug import sensitive_variables

from .models import Competition

API = "https://discord.com/api/v10"
INVITE_BASE = "https://discord.gg/"
VOICE_CHANNEL = 2  # Discord's type of a voice channel
CHANNEL_NAME_MAX = 100  # Discord's longest channel name
# Discord's codes for a server or a category with no room for another channel (500 on a server, 50 in a category)
_NO_ROOM_CODES = ("30013", "CHANNEL_PARENT_MAX_CHANNELS")
# Saving an event waits for Discord on one of the site's request threads: a slow Discord fails the room, which the
# next save opens, rather than hold the thread
_TIMEOUT = 10
# the line the room's invitation takes in an event's text: one of its own, so a cloned event's old room is let go
_ROOM_LINE = re.compile(r'<p>[^<]*<a href="https://discord\.gg/[\w-]+"[^>]*>[^<]*</a></p>')


logger = logging.getLogger(__name__)
# the day after the event's last one is the room's too: it closes once that day is over at the event's place
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
    except ValueError:  # a proxy's page in place of Discord's answer: the event is saved already, the room waits
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
    """Why Discord refused, in the words that say what to set up: the organizer passes them on to the admin."""
    if status == HTTPStatus.BAD_REQUEST and any(code in body for code in _NO_ROOM_CODES):
        return _("the server or its category has no room for another channel: 500 on a server, 50 in a category")
    if status == HTTPStatus.UNAUTHORIZED:
        return _("Discord does not accept the site's bot token")
    if status == HTTPStatus.FORBIDDEN:
        return _("the bot may not create channels or invitations on the server")
    if status == HTTPStatus.NOT_FOUND:
        return _("Discord does not know the server or the category the site names")
    return f"Discord answered {status}"


def _channel_name(competition: Competition) -> str:
    """The event's title as a channel's name -- lower case, words joined by dashes -- with its date."""
    words = slugify(competition.title_ru or competition.title or "", allow_unicode=True) or f"event-{competition.pk}"
    return f"{competition.date_start:%Y-%m-%d}-{words}"[:CHANNEL_NAME_MAX]


def _with_room(text: str, line: str) -> str:
    """The event's text with the room's line at its end, in place of a line an earlier room left there."""
    return (_ROOM_LINE.sub("", text or "").rstrip() + line).strip()


def _write_invitation(competition: Competition, url: str) -> None:
    """The invitation in the event's text in each language that has one; in all three when none has."""
    filled = [lang for lang in ("ru", "kk", "en") if (getattr(competition, f"description_{lang}") or "").strip()]
    for lang in filled or ["ru", "kk", "en"]:
        with override(lang):
            line = f'<p>{_("Discord room")}: <a href="{url}">{url}</a></p>'
        field = f"description_{lang}"
        setattr(competition, field, _with_room(getattr(competition, field), line))


def open_room(competition: Competition) -> str:
    """Open the event's Discord room if its box asks for one it does not have yet.

    Answers what the organizer is told: "" when there is nothing to say -- a room opened, already there or not
    asked for --, else why there is none yet.
    """
    if not competition.discord_room or competition.discord_invite_url or is_over(competition):
        return ""
    if not configured():
        return _("Discord is not set up on this site yet: the room is opened once it is, on the event's next save.")
    try:
        if not competition.discord_channel_id:
            channel = _post(
                f"/guilds/{settings.DISCORD_GUILD_ID}/channels",
                {
                    "name": _channel_name(competition),
                    "type": VOICE_CHANNEL,
                    **({"parent_id": settings.DISCORD_CATEGORY_ID} if settings.DISCORD_CATEGORY_ID else {}),
                },
            )
            competition.discord_channel_id = str(channel["id"])
            # kept at once: an invitation that fails is made in this channel on the next save, not in a second one
            Competition.objects.filter(pk=competition.pk).update(discord_channel_id=competition.discord_channel_id)
        # an invitation that never runs out and takes any number of people
        invite = _post(
            f"/channels/{competition.discord_channel_id}/invites", {"max_age": 0, "max_uses": 0, "unique": False}
        )
        competition.discord_invite_url = f"{INVITE_BASE}{invite['code']}"
    except (DiscordError, KeyError) as exc:
        return _("The Discord room could not be opened (%(reason)s): saving the event again tries once more.") % {
            "reason": exc
        }
    _write_invitation(competition, competition.discord_invite_url)
    competition.save(
        update_fields=["discord_invite_url", "description_ru", "description_kk", "description_en", "updated_at"]
    )
    return ""


def is_over(competition: Competition) -> bool:
    """The event and the day after it are over at its place: its room is closed, and none is opened."""
    today = timezone.localdate(timezone=competition.timezone)
    return today > competition.last_day + datetime.timedelta(days=_DAYS_KEPT)


def close_due_rooms() -> int:
    """Delete the channels of the events that are over, take their invitations out of the texts; how many closed.

    Deleted events' rooms too. A room Discord fails to delete, or one past ``CLOSE_PER_CALL`` or
    ``CLOSE_SECONDS``, is left for the next night.
    """
    if not settings.DISCORD_BOT_TOKEN:
        return 0
    # a superset by UTC's date -- a place ahead of UTC is a day further on -- narrowed by each event's own zone
    latest = timezone.now().date() - datetime.timedelta(days=_DAYS_KEPT)
    due = (
        Competition.objects.exclude(discord_channel_id="")
        .annotate(last=Coalesce("date_end", "date_start"))
        .filter(last__lte=latest)
        .select_related("location")
        .order_by("last", "pk")[:CLOSE_PER_CALL]
    )
    closed, started = 0, time.monotonic()
    for competition in due:
        if time.monotonic() - started > CLOSE_SECONDS:
            break
        if not is_over(competition):
            continue
        try:
            _delete_channel(competition.discord_channel_id)
        except DiscordError as exc:
            logger.warning("Discord room of event %s not closed: %s", competition.pk, exc)
            continue
        texts = {
            f"description_{lang}": _ROOM_LINE.sub("", getattr(competition, f"description_{lang}") or "").strip()
            for lang in ("ru", "kk", "en")
        }
        # an update, not a save: the event's own fields and its review are not the room's to touch
        Competition.objects.filter(pk=competition.pk).update(discord_channel_id="", discord_invite_url="", **texts)
        closed += 1
    return closed
