"""A Discord room for an event: a text channel the site's bot opens on the club's server, and its invitation.

An organizer ticks the event form's box "Create a Discord room" (``Competition.discord_room``); once the event is
saved the site opens a text channel named after it, under the category ``DISCORD_CATEGORY_ID`` names where one is
set, makes an invitation that never runs out and writes it into the event's text in each language. The room is
opened once: the channel and its invitation stay with the event (``discord_channel_id``, ``discord_invite_url``),
and unticking the box later leaves the room on Discord. A failure keeps the event and its box, and the next save
tries again. Every call goes through ``requests``, which the tests patch -- they never reach Discord.
"""

import re
from http import HTTPStatus

import requests
from django.conf import settings
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import override
from django.views.decorators.debug import sensitive_variables

from .models import Competition

API = "https://discord.com/api/v10"
INVITE_BASE = "https://discord.gg/"
TEXT_CHANNEL = 0  # Discord's type of a text channel
CHANNEL_NAME_MAX = 100  # Discord's longest channel name
TOPIC_MAX = 1024
# Saving an event waits for Discord on one of the site's request threads: a slow Discord fails the room, which the
# next save opens, rather than hold the thread
_TIMEOUT = 10
# the line the room's invitation takes in an event's text: one of its own, so a cloned event's old room is let go
_ROOM_LINE = re.compile(r'<p>[^<]*<a href="https://discord\.gg/[\w-]+"[^>]*>[^<]*</a></p>')


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
        raise DiscordError(f"Discord answered {response.status_code}")
    return response.json()


def _channel_name(competition: Competition) -> str:
    """The event's title as Discord names a text channel -- lower case, words joined by dashes -- with its date."""
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
    if not competition.discord_room or competition.discord_invite_url:
        return ""
    if not configured():
        return _("Discord is not set up on this site yet: the room is opened once it is, on the event's next save.")
    try:
        if not competition.discord_channel_id:
            channel = _post(
                f"/guilds/{settings.DISCORD_GUILD_ID}/channels",
                {
                    "name": _channel_name(competition),
                    "type": TEXT_CHANNEL,
                    "topic": f"{settings.SITE_BASE_URL}{competition.get_absolute_url()}"[:TOPIC_MAX],
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
