"""A Discord room for a virtual race: the host's box, the voice channel the site's bot opens, its closing."""

import datetime
import json
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.utils.translation import gettext

from accounts.models import User
from calendar_app.models import Competition
from cycling_site.sanitize import sanitize_rich_html
from trainer import discord
from trainer.models import GroupRide

API = "/api/v1/virtual-ride"
DISCORD_ON = {"DISCORD_BOT_TOKEN": "bot-tok-7c1e", "DISCORD_GUILD_ID": "111", "DISCORD_CATEGORY_ID": "222"}
INVITE = "https://discord.gg/AbC12"


def _user(name, role):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)


def _answer(status, body=None):
    response = mock.Mock(status_code=status, text="")
    response.json.return_value = body or {}
    return response


def _discord(url, json=None, **kw):
    """Discord as a working bot meets it: a channel, then an invitation to it."""
    if url.endswith("/guilds/111/channels"):
        return _answer(201, {"id": "333", "name": json["name"]})
    if url.endswith("/channels/333/invites"):
        return _answer(200, {"code": "AbC12"})
    return _answer(404)


def _at(utc):
    """The site's clock at ``utc``."""
    return mock.patch("django.utils.timezone.now", return_value=utc)


@override_settings(**DISCORD_ON)
class GatheringWithARoomTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = _user("org", User.Role.ORGANIZER)
        cls.participant = _user("part", User.Role.PARTICIPANT)

    def client_of(self, user):
        client = Client()
        client.force_login(user)
        return client

    def gather(self, user, **extra):
        body = {"route": "center", "route_name": "Central loop", "start_in_s": 600, "discord_room": True, **extra}
        return self.client_of(user).post(f"{API}/groups", json.dumps(body), content_type="application/json")

    @mock.patch("trainer.discord.requests.post", side_effect=_discord)
    def test_an_organizer_s_race_gets_a_voice_room_its_card_shows(self, post):
        answer = self.gather(self.organizer)
        self.assertEqual(answer.status_code, 201)
        self.assertEqual((answer.json()["discord_invite_url"], answer.json()["discord_note"]), (INVITE, ""))
        group = GroupRide.objects.get()
        self.assertEqual((group.discord_channel_id, group.discord_invite_url), ("333", INVITE))
        channel = post.call_args_list[0].kwargs
        self.assertEqual(channel["headers"], {"Authorization": "Bot bot-tok-7c1e"})
        self.assertEqual(channel["json"]["type"], discord.VOICE_CHANNEL)
        self.assertEqual(channel["json"]["parent_id"], "222")
        start = timezone.localtime(group.start_at, timezone.get_default_timezone())  # no zone sent: the site's
        self.assertEqual(channel["json"]["name"], f"{start:%Y-%m-%d %H:%M} Central loop")
        # an invitation that never runs out
        self.assertEqual(post.call_args_list[1].kwargs["json"], {"max_age": 0, "max_uses": 0, "unique": False})
        # every rider who sees the race sees its room
        listed = self.client_of(self.participant).get(f"{API}/groups").json()
        self.assertEqual(listed[0]["discord_invite_url"], INVITE)

    @mock.patch("trainer.discord.requests.post", side_effect=_discord)
    def test_the_room_is_named_by_the_start_on_its_host_s_clock(self, post):
        client = self.client_of(self.organizer)
        client.cookies["tz"] = "Asia/Tokyo"
        body = {"route": "center", "route_name": "Central loop", "start_in_s": 600, "discord_room": True}
        client.post(f"{API}/groups", json.dumps(body), content_type="application/json")
        start = timezone.localtime(GroupRide.objects.get().start_at, ZoneInfo("Asia/Tokyo"))
        self.assertEqual(post.call_args_list[0].kwargs["json"]["name"], f"{start:%Y-%m-%d %H:%M} Central loop")

    @mock.patch("trainer.discord.requests.post", side_effect=_discord)
    def test_without_the_box_no_room_is_opened(self, post):
        self.assertEqual(self.gather(self.organizer, discord_room=False).json()["discord_invite_url"], "")
        post.assert_not_called()

    @mock.patch("trainer.discord.requests.post", side_effect=_discord)
    def test_a_participant_may_not_ask_for_a_room(self, post):
        self.assertEqual(self.gather(self.participant).status_code, 403)
        self.assertFalse(GroupRide.objects.exists())
        post.assert_not_called()

    def test_the_box_is_offered_to_organizers_on_a_site_with_a_bot(self):
        for user, offered in ((self.organizer, True), (self.participant, False)):
            with self.subTest(user=user.username):
                self.assertIs(self.client_of(user).get(f"{API}/me").json()["discord_rooms"], offered)
        with override_settings(DISCORD_BOT_TOKEN=""):
            self.assertIs(self.client_of(self.organizer).get(f"{API}/me").json()["discord_rooms"], False)

    @mock.patch("trainer.discord.requests.post")
    def test_discord_s_refusal_keeps_the_race_and_says_why(self, post):
        post.return_value = _answer(403)
        answer = self.gather(self.organizer)
        self.assertEqual(answer.status_code, 201)
        said = gettext("the bot may not create channels or invitations on the server")
        self.assertIn(said, answer.json()["discord_note"])
        self.assertEqual(GroupRide.objects.get().discord_invite_url, "")

    @mock.patch("trainer.discord.requests.post")
    def test_a_category_with_no_room_for_another_channel_is_said_in_words(self, post):
        post.return_value = _answer(400)
        post.return_value.text = (
            '{"code": 50035, "errors": {"parent_id": {"_errors": [{"code": "CHANNEL_PARENT_MAX_CHANNELS",'
            ' "message": "Maximum number of channels in category reached (50)"}]}}, "message": "Invalid Form Body"}'
        )
        said = gettext("the server or its category has no room for another channel: 500 on a server, 50 in a category")
        self.assertIn(said, self.gather(self.organizer).json()["discord_note"])

    @mock.patch("trainer.discord.requests.post")
    def test_an_answer_that_is_not_discord_s_is_said(self, post):
        post.return_value = _answer(200)
        post.return_value.json.side_effect = ValueError("not JSON")
        self.assertIn("Discord answered without JSON", self.gather(self.organizer).json()["discord_note"])

    def test_the_room_s_line_in_an_event_s_text_comes_through_the_sanitizer_as_the_closing_finds_it(self):
        """group-ride.js writes the line; what the site keeps of it must still be the line it takes out."""
        line = f'<p>Voice room on Discord: <a href="{INVITE}">{INVITE}</a></p>'
        kept = sanitize_rich_html(f"<p>Start at 18:00.</p>{line}")
        pattern = discord._ROOM_LINE.format(url=discord.re.escape(INVITE))
        self.assertEqual(discord.re.sub(pattern, "", kept), "<p>Start at 18:00.</p>")


@override_settings(**DISCORD_ON)
class RoomClosingTests(TestCase):
    """A room lasts the day of the start and the whole day after it, then its channel is deleted."""

    START = datetime.datetime(2026, 12, 1, 18, 0, tzinfo=datetime.UTC)

    def setUp(self):
        self.host = _user("host", User.Role.ORGANIZER)
        self.group = GroupRide.objects.create(
            route="center",
            route_name="Central loop",
            host=self.host,
            start_at=self.START,
            discord_channel_id="333",
            discord_invite_url=INVITE,
        )
        line = f'<p>Voice room on Discord: <a href="{INVITE}">{INVITE}</a></p>'
        self.other = '<p>Our server: <a href="https://discord.gg/Club1">https://discord.gg/Club1</a></p>'
        self.event = Competition.objects.create(
            title_ru="Night race",
            date_start=self.START.date(),
            description_ru=f"<p>Start at 18:00.</p>{self.other}{line}",
            virtual_ride=self.group.pk,
        )

    def close(self, utc, status=200):
        with _at(utc), mock.patch("trainer.discord.requests.delete", return_value=_answer(status)) as delete:
            closed = discord.close_due_rooms()
        self.group.refresh_from_db()
        self.event.refresh_from_db()
        return closed, delete

    def test_the_day_after_the_start_the_room_stays(self):
        closed, delete = self.close(datetime.datetime(2026, 12, 2, 23, 59, tzinfo=datetime.UTC))
        self.assertEqual((closed, self.group.discord_channel_id), (0, "333"))
        delete.assert_not_called()

    def test_once_the_day_after_is_over_its_channel_goes_and_its_line_leaves_the_event_s_text(self):
        closed, delete = self.close(datetime.datetime(2026, 12, 3, 0, 1, tzinfo=datetime.UTC))
        self.assertEqual(closed, 1)
        self.assertEqual(delete.call_args.args[0], f"{discord.API}/channels/333")
        self.assertEqual(delete.call_args.kwargs["headers"], {"Authorization": "Bot bot-tok-7c1e"})
        self.assertEqual((self.group.discord_channel_id, self.group.discord_invite_url), ("", ""))
        # the organizer's own link to another server stays
        self.assertNotIn("AbC12", self.event.description_ru)
        self.assertIn("https://discord.gg/Club1</a></p>", self.event.description_ru)

    def test_the_days_are_counted_at_the_place_of_the_race_s_event(self):
        from locations.models import Location

        tokyo = Location.add_root(name_ru="Tokyo", name_en="Tokyo", lat="35.689500", lng="139.691700")
        Competition.objects.filter(pk=self.event.pk).update(location=tokyo)
        # 18:00 UTC on the 1st is the 2nd in Tokyo: the room is the 2nd's and the 3rd's, there
        self.assertEqual(self.close(datetime.datetime(2026, 12, 3, 12, 0, tzinfo=datetime.UTC))[0], 0)
        self.assertEqual(self.close(datetime.datetime(2026, 12, 3, 15, 30, tzinfo=datetime.UTC))[0], 1)

    def test_a_cancelled_race_s_room_goes_the_next_night(self):
        GroupRide.objects.filter(pk=self.group.pk).update(cancelled=True)
        self.assertEqual(self.close(self.START - datetime.timedelta(hours=1))[0], 1)

    def test_a_channel_already_gone_counts_as_closed(self):
        self.assertEqual(self.close(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC), status=404)[0], 1)

    def test_a_room_discord_does_not_delete_waits_for_the_next_night(self):
        with self.assertLogs("trainer.discord", "WARNING"):
            closed, _delete = self.close(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC), status=403)
        self.assertEqual((closed, self.group.discord_channel_id), (0, "333"))

    def test_one_night_closes_a_bounded_number_of_rooms_the_oldest_first(self):
        older = GroupRide.objects.create(
            route="center", host=self.host, start_at=self.START - datetime.timedelta(days=1), discord_channel_id="111"
        )
        with mock.patch.object(discord, "CLOSE_PER_CALL", 1):
            closed, delete = self.close(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC))
        self.assertEqual((closed, delete.call_args.args[0]), (1, f"{discord.API}/channels/111"))
        older.refresh_from_db()
        self.assertEqual((older.discord_channel_id, self.group.discord_channel_id), ("", "333"))

    def test_a_slow_discord_leaves_the_rest_for_the_next_night(self):
        GroupRide.objects.create(route="center", host=self.host, start_at=self.START, discord_channel_id="111")
        clock = iter([0, 1, discord.CLOSE_SECONDS + 1])
        with mock.patch("trainer.discord.time.monotonic", side_effect=lambda: next(clock)):
            closed, delete = self.close(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC))
        self.assertEqual((closed, delete.call_count), (1, 1))

    def test_the_nightly_call_is_open_and_says_how_many_closed(self):
        with (
            _at(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC)),
            mock.patch("trainer.discord.requests.delete", return_value=_answer(204)),
        ):
            answer = Client().post(f"{API}/discord-rooms/close-due")
        self.assertEqual((answer.status_code, answer.json()), (200, {"closed": 1}))
