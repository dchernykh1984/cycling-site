"""A Discord room for an event: the organizer's box, the channel the site's bot opens, its invitation in the text."""

import datetime
import json
import uuid
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import override as translation_override

from accounts.models import User
from calendar_app import discord
from calendar_app.models import Competition

DISCORD_ON = {"DISCORD_BOT_TOKEN": "bot-tok-7c1e", "DISCORD_GUILD_ID": "111", "DISCORD_CATEGORY_ID": "222"}


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


def _payload(**extra):
    payload = {
        "title_ru": "Night race",
        "description_ru": "<p>Start at 22:00.</p>",
        "date_start": f"{timezone.localdate() + datetime.timedelta(days=9):%Y-%m-%d}",
        "discord_room": "on",
    }
    payload.update(extra)
    return payload


@override_settings(**DISCORD_ON)
class DiscordRoomFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = _user("org", User.Role.ORGANIZER)
        cls.participant = _user("part", User.Role.PARTICIPANT)

    def submit(self, user, **extra):
        self.client.force_login(user)
        return self.client.post(reverse("calendar_submit"), _payload(**extra), follow=True)

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_an_organizer_s_box_opens_a_room_and_its_invitation_goes_into_the_text(self, post):
        self.submit(self.organizer)
        event = Competition.objects.get(title_ru="Night race")
        self.assertEqual(
            (event.discord_room, event.discord_channel_id, event.discord_invite_url),
            (True, "333", "https://discord.gg/AbC12"),
        )
        channel = post.call_args_list[0]
        self.assertEqual(channel.kwargs["headers"], {"Authorization": "Bot bot-tok-7c1e"})
        self.assertEqual(channel.kwargs["json"]["type"], discord.VOICE_CHANNEL)
        self.assertEqual(channel.kwargs["json"]["parent_id"], "222")
        self.assertEqual(channel.kwargs["json"]["name"], f"{event.date_start:%Y-%m-%d}-night-race")
        # an invitation that never runs out
        self.assertEqual(post.call_args_list[1].kwargs["json"], {"max_age": 0, "max_uses": 0, "unique": False})
        # the line in the text the event has, in its language; the others fall back to it
        with translation_override("ru"):
            said = gettext("Discord room")
        self.assertTrue(
            event.description_ru.startswith(f'<p>Start at 22:00.</p><p>{said}: <a href="https://discord.gg/AbC12"')
        )
        self.assertTrue(event.description_ru.endswith(">https://discord.gg/AbC12</a></p>"))
        self.assertFalse(event.description_kk)

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_an_event_without_text_gets_the_line_in_every_language(self, post):
        self.submit(self.organizer, description_ru="")
        event = Competition.objects.get(title_ru="Night race")
        for lang in ("ru", "kk", "en"):
            with translation_override(lang):
                said = gettext("Discord room")
            self.assertIn(f"<p>{said}: <a", getattr(event, f"description_{lang}"))

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_a_participant_s_box_is_not_read(self, post):
        self.submit(self.participant)
        self.assertFalse(Competition.objects.get(title_ru="Night race").discord_room)
        post.assert_not_called()

    def test_the_box_is_offered_to_organizers_only(self):
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(reverse("calendar_submit")), 'name="discord_room"')
        self.client.force_login(self.participant)
        self.assertNotContains(self.client.get(reverse("calendar_submit")), 'name="discord_room"')

    @mock.patch("calendar_app.discord.requests.post")
    def test_a_room_is_opened_once_whatever_saves_the_event_after(self, post):
        post.side_effect = _discord
        self.submit(self.organizer)
        event = Competition.objects.get(title_ru="Night race")
        self.client.post(
            reverse("competition_edit", args=[event.pk]),
            _payload(title_ru="Night race 2", description_ru=event.description_ru),
        )
        self.assertEqual(post.call_count, 2)  # the channel and its invitation, once
        event.refresh_from_db()
        self.assertEqual((event.title_ru, event.description_ru.count("discord.gg")), ("Night race 2", 2))

    @mock.patch("calendar_app.discord.requests.post")
    def test_a_failed_invitation_keeps_its_channel_and_the_next_save_makes_it_there(self, post):
        post.side_effect = lambda url, **kw: _answer(500) if url.endswith("/invites") else _discord(url, **kw)
        page = self.submit(self.organizer)
        event = Competition.objects.get(title_ru="Night race")
        self.assertEqual((event.discord_channel_id, event.discord_invite_url), ("333", ""))
        self.assertContains(page, "Discord answered 500")
        post.side_effect = _discord
        post.reset_mock()
        self.client.post(reverse("competition_edit", args=[event.pk]), _payload(description_ru=event.description_ru))
        event.refresh_from_db()
        self.assertEqual(event.discord_invite_url, "https://discord.gg/AbC12")
        self.assertEqual([c.args[0].rsplit("/", 2)[-2:] for c in post.call_args_list], [["333", "invites"]])

    @mock.patch("calendar_app.discord.requests.post")
    def test_a_category_with_no_room_for_another_channel_is_said_in_words(self, post):
        post.return_value = _answer(400)
        post.return_value.text = (
            '{"code": 50035, "errors": {"parent_id": {"_errors": [{"code": "CHANNEL_PARENT_MAX_CHANNELS",'
            ' "message": "Maximum number of channels in category reached (50)"}]}}, "message": "Invalid Form Body"}'
        )
        page = self.submit(self.organizer)
        self.assertContains(
            page,
            gettext("the server or its category has no room for another channel: 500 on a server, 50 in a category"),
        )
        self.assertEqual(Competition.objects.get(title_ru="Night race").discord_channel_id, "")

    @mock.patch("calendar_app.discord.requests.post")
    def test_an_answer_that_is_not_discord_s_keeps_the_event_and_says_so(self, post):
        post.return_value = _answer(200)
        post.return_value.json.side_effect = ValueError("not JSON")
        page = self.submit(self.organizer)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(Competition.objects.get(title_ru="Night race").discord_invite_url, "")
        self.assertContains(page, "Discord answered without JSON")

    @mock.patch("calendar_app.discord.requests.post")
    def test_without_the_bot_the_box_waits_and_the_organizer_is_told(self, post):
        with override_settings(DISCORD_BOT_TOKEN=""):
            page = self.submit(self.organizer)
        event = Competition.objects.get(title_ru="Night race")
        self.assertTrue(event.discord_room)
        self.assertEqual(event.discord_invite_url, "")
        said = gettext(
            "Discord is not set up on this site yet: the room is opened once it is, on the event's next save."
        )
        self.assertEqual([str(m) for m in page.context["messages"]], [said])
        post.assert_not_called()

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_a_copy_of_an_event_with_a_room_keeps_the_box_and_gets_a_room_of_its_own(self, post):
        self.submit(self.organizer)
        source = Competition.objects.get(title_ru="Night race")
        form = self.client.get(reverse("calendar_submit"), {"clone": source.pk}).context["form"]
        self.assertTrue(form.initial["discord_room"])
        post.side_effect = lambda url, json=None, **kw: (
            _answer(201, {"id": "444"}) if url.endswith("/channels") else _answer(200, {"code": "New9"})
        )
        self.client.post(reverse("calendar_submit"), _payload(title_ru="Copy", description_ru=source.description_ru))
        copy = Competition.objects.get(title_ru="Copy")
        # the old room's line gives way to its own
        self.assertNotIn("AbC12", copy.description_ru)
        self.assertEqual(copy.description_ru.count("https://discord.gg/New9"), 2)

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_the_edit_page_shows_the_room(self, post):
        self.submit(self.organizer)
        event = Competition.objects.get(title_ru="Night race")
        self.assertContains(
            self.client.get(reverse("competition_edit", args=[event.pk])), 'href="https://discord.gg/AbC12"'
        )


@override_settings(**DISCORD_ON)
class DiscordRoomApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = _user("org", User.Role.ORGANIZER)
        cls.participant = _user("part", User.Role.PARTICIPANT)

    def call(self, method, path, user, body):
        if user.api_token is None:
            user.api_token = uuid.uuid4()
            user.save(update_fields=["api_token"])
        return getattr(self.client, method)(
            f"/api/v1/competitions{path}",
            json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {user.api_token}",
        )

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_an_event_made_through_the_api_gets_its_room(self, post):
        body = {"title": {"ru": "API race"}, "date_start": f"{timezone.localdate():%Y-%m-%d}", "discord_room": True}
        answer = self.call("post", "/", self.organizer, body).json()
        self.assertEqual(
            (answer["discord_room"], answer["discord_invite_url"], answer["discord_note"]),
            (True, "https://discord.gg/AbC12", ""),
        )
        self.assertIn("https://discord.gg/AbC12", answer["description"]["ru"])

    @mock.patch("calendar_app.discord.requests.post", return_value=_answer(403))
    def test_discord_s_refusal_is_said_in_the_answer(self, post):
        event = Competition.objects.create(
            title_ru="Patched", date_start=timezone.localdate(), submitted_by=self.organizer
        )
        answer = self.call("patch", f"/{event.pk}", self.organizer, {"discord_room": True}).json()
        self.assertEqual(answer["discord_invite_url"], "")
        self.assertIn(gettext("the bot may not create channels or invitations on the server"), answer["discord_note"])

    def test_a_participant_author_cannot_ask_for_a_room(self):
        event = Competition.objects.create(
            title_ru="Own", date_start=timezone.localdate(), submitted_by=self.participant
        )
        self.assertEqual(self.call("patch", f"/{event.pk}", self.participant, {"discord_room": True}).status_code, 403)


def _at(utc):
    """The site's clock at ``utc``."""
    return mock.patch("django.utils.timezone.now", return_value=utc)


@override_settings(**DISCORD_ON)
class DiscordRoomClosingTests(TestCase):
    """A room lasts the event and the whole day after it at the event's place, then its channel is deleted."""

    LAST_DAY = datetime.date(2026, 12, 1)

    def setUp(self):
        line = '<p>Discord room: <a href="https://discord.gg/AbC12">https://discord.gg/AbC12</a></p>'
        self.event = Competition.objects.create(
            title_ru="Night race",
            date_start=self.LAST_DAY,
            description_ru=f"<p>Start at 22:00.</p>{line}",
            discord_room=True,
            discord_channel_id="333",
            discord_invite_url="https://discord.gg/AbC12",
        )

    def close(self, utc):
        with _at(utc), mock.patch("calendar_app.discord.requests.delete", return_value=_answer(200)) as delete:
            closed = discord.close_due_rooms()
        self.event.refresh_from_db()
        return closed, delete

    def test_the_day_after_the_event_the_room_stays(self):
        closed, delete = self.close(datetime.datetime(2026, 12, 2, 23, 59, tzinfo=datetime.UTC))
        self.assertEqual((closed, self.event.discord_channel_id), (0, "333"))
        delete.assert_not_called()

    def test_once_the_day_after_is_over_its_channel_is_deleted_and_its_line_leaves_the_text(self):
        closed, delete = self.close(datetime.datetime(2026, 12, 3, 0, 1, tzinfo=datetime.UTC))
        self.assertEqual(closed, 1)
        self.assertEqual(delete.call_args.args[0], f"{discord.API}/channels/333")
        self.assertEqual(delete.call_args.kwargs["headers"], {"Authorization": "Bot bot-tok-7c1e"})
        self.assertEqual((self.event.discord_channel_id, self.event.discord_invite_url), ("", ""))
        self.assertEqual(self.event.description_ru, "<p>Start at 22:00.</p>")
        self.assertTrue(self.event.discord_room)  # the organizer's box stays as they left it

    def test_the_day_after_is_counted_at_the_event_s_place(self):
        from locations.models import Location

        tokyo = Location.add_root(name_ru="Tokyo", name_en="Tokyo", lat="35.689500", lng="139.691700")
        Competition.objects.filter(pk=self.event.pk).update(location=tokyo)
        # 15:30 UTC on the 2nd is already 00:30 on the 3rd in Tokyo
        closed, _delete = self.close(datetime.datetime(2026, 12, 2, 15, 30, tzinfo=datetime.UTC))
        self.assertEqual(closed, 1)

    def test_a_channel_already_gone_counts_as_closed(self):
        with (
            _at(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC)),
            mock.patch("calendar_app.discord.requests.delete", return_value=_answer(404)),
        ):
            self.assertEqual(discord.close_due_rooms(), 1)

    def test_a_room_discord_does_not_delete_waits_for_the_next_night(self):
        with (
            _at(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC)),
            mock.patch("calendar_app.discord.requests.delete", return_value=_answer(403)),
            self.assertLogs("calendar_app.discord", "WARNING"),
        ):
            self.assertEqual(discord.close_due_rooms(), 0)
        self.event.refresh_from_db()
        self.assertEqual(self.event.discord_channel_id, "333")

    def test_a_deleted_event_s_room_is_closed_too(self):
        Competition.objects.filter(pk=self.event.pk).update(is_deleted=True)
        self.assertEqual(self.close(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC))[0], 1)

    @mock.patch("calendar_app.discord.requests.post", side_effect=_discord)
    def test_an_event_that_is_over_opens_no_room(self, post):
        self.event.discord_invite_url = ""
        self.event.discord_channel_id = ""
        with _at(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC)):
            self.assertEqual(discord.open_room(self.event), "")
        post.assert_not_called()

    def test_the_nightly_call_is_open_and_says_how_many_closed(self):
        with (
            _at(datetime.datetime(2026, 12, 5, tzinfo=datetime.UTC)),
            mock.patch("calendar_app.discord.requests.delete", return_value=_answer(204)),
        ):
            answer = self.client.post("/api/v1/competitions/discord-rooms/close-due")
        self.assertEqual((answer.status_code, answer.json()), (200, {"closed": 1}))
