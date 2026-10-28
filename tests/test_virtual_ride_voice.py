"""Voice chat in a group race: the site introduces the riders to the media server and keeps the key."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from tests.test_virtual_ride_api import API, MemberClientMixin, _user
from trainer.live import ONLINE_SECONDS
from trainer.models import GroupRide, GroupRideMember, LiveRider, VoiceSession

VOICE_ON = {"CLOUDFLARE_REALTIME_APP_ID": "app1", "CLOUDFLARE_REALTIME_APP_SECRET": "s3cret"}


def _answer(status, body):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    return response


@override_settings(**VOICE_ON)
class VoiceChatTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.host, self.guest = _user("anna"), _user("boris")
        self.group = GroupRide.objects.create(
            route="center", host=self.host, start_at=timezone.now() + timedelta(minutes=5)
        )
        for user in (self.host, self.guest):
            GroupRideMember.objects.create(group=self.group, user=user)
            LiveRider.objects.create(user=user, updated_at=timezone.now())
        self.client_h, self.client_g = self.member(self.host), self.member(self.guest)

    def in_voice(self, user, key):
        return VoiceSession.objects.create(user=user, group=self.group, session_id=f"S-{key}", track_name=key, mid="0")

    def join(self, client, **body):
        return self.post(client, f"/groups/{self.group.pk}/voice", {"offer": "v=0 offer", "mid": "0", **body})

    @mock.patch("trainer.voice.requests.request")
    def test_a_rider_of_the_race_publishes_their_microphone_through_the_media_server(self, call):
        call.side_effect = [
            _answer(201, {"sessionId": "S1"}),
            _answer(200, {"sessionDescription": {"type": "answer", "sdp": "v=0 answer"}, "tracks": [{"mid": "0"}]}),
        ]
        joined = self.join(self.client_g)
        self.assertEqual(joined.json(), {"answer": "v=0 answer"})
        (method_1, url_1), (method_2, url_2) = (c.args for c in call.call_args_list)
        self.assertEqual((method_1, url_1), ("POST", "https://rtc.live.cloudflare.com/v1/apps/app1/sessions/new"))
        self.assertEqual(
            (method_2, url_2), ("POST", "https://rtc.live.cloudflare.com/v1/apps/app1/sessions/S1/tracks/new")
        )
        sent = call.call_args.kwargs
        self.assertEqual(sent["headers"]["Authorization"], "Bearer s3cret")
        self.assertEqual(sent["json"]["sessionDescription"], {"type": "offer", "sdp": "v=0 offer"})
        mine = VoiceSession.objects.get(user=self.guest)
        self.assertEqual((mine.session_id, mine.mid), ("S1", "0"))
        self.assertEqual(sent["json"]["tracks"], [{"location": "local", "mid": "0", "trackName": mine.track_name}])

    def test_only_the_race_s_riders_join_and_only_where_voice_is_offered(self):
        outsider = self.member(_user("carl"))
        self.assertEqual(self.join(outsider).status_code, 403)
        self.group.cancelled = True
        self.group.save()
        self.assertEqual(self.join(self.client_g).status_code, 409)
        with override_settings(CLOUDFLARE_REALTIME_APP_ID=""):
            self.assertEqual(self.join(self.client_g).status_code, 404)
            self.assertFalse(self.client_g.get(f"{API}/me").json()["voice_available"])
        self.assertTrue(self.client_g.get(f"{API}/me").json()["voice_available"])

    @override_settings(VOICE_MAX_RIDERS=1)
    def test_a_full_chat_takes_nobody_else(self):
        self.in_voice(self.host, "k-host")
        self.assertEqual(self.join(self.client_g).status_code, 409)

    def test_presence_says_who_is_in_the_chat_and_never_their_sessions(self):
        self.in_voice(self.host, "k-host")
        gone = _user("dina")
        GroupRideMember.objects.create(group=self.group, user=gone)
        LiveRider.objects.create(user=gone, updated_at=timezone.now() - timedelta(seconds=ONLINE_SECONDS + 5))
        self.in_voice(gone, "k-gone")  # closed the page: not in the chat any more
        body = self.post(self.client_g, "/presence", {"status": "lobby"}).json()
        self.assertEqual(body["voice_group_id"], self.group.pk)
        self.assertEqual(
            body["voice"], [{"user_id": self.host.pk, "name": self.host.public_display_name, "key": "k-host"}]
        )
        self.assertNotIn("S-k-host", str(body))

    @mock.patch("trainer.voice.requests.request")
    def test_hearing_the_others_maps_their_sound_to_them_and_stays_in_the_race(self, call):
        self.in_voice(self.guest, "k-guest")
        self.in_voice(self.host, "k-host")
        stranger = _user("eve")
        other = GroupRide.objects.create(route="center", host=stranger, start_at=timezone.now() + timedelta(minutes=5))
        VoiceSession.objects.create(user=stranger, group=other, session_id="S-x", track_name="k-x", mid="0")
        call.return_value = _answer(
            200,
            {
                "requiresImmediateRenegotiation": True,
                "sessionDescription": {"type": "offer", "sdp": "v=0 pull"},
                "tracks": [{"sessionId": "S-k-host", "trackName": "k-host", "mid": "1"}],
            },
        )
        heard = self.post(self.client_g, f"/groups/{self.group.pk}/voice/pull", {"keys": ["k-host", "k-x"]}).json()
        self.assertEqual(heard["offer"], "v=0 pull")
        self.assertEqual(heard["tracks"], [{"key": "k-host", "user_id": self.host.pk, "mid": "1"}])
        self.assertEqual(heard["failed"], ["k-x"])  # another race's rider is never pulled
        self.assertEqual(
            call.call_args.args[1], "https://rtc.live.cloudflare.com/v1/apps/app1/sessions/S-k-guest/tracks/new"
        )
        self.assertEqual(
            call.call_args.kwargs["json"]["tracks"],
            [{"location": "remote", "sessionId": "S-k-host", "trackName": "k-host"}],
        )

    def test_hearing_needs_joining_first(self):
        self.in_voice(self.host, "k-host")
        self.assertEqual(
            self.post(self.client_g, f"/groups/{self.group.pk}/voice/pull", {"keys": ["k-host"]}).status_code, 409
        )

    @mock.patch("trainer.voice.requests.request")
    def test_the_answer_finishes_the_negotiation_and_leaving_closes_the_microphone(self, call):
        self.in_voice(self.guest, "k-guest")
        call.return_value = _answer(200, {})
        answered = self.post(self.client_g, f"/groups/{self.group.pk}/voice/answer", {"answer": "v=0 answer"})
        self.assertEqual(answered.status_code, 204)
        self.assertEqual(
            call.call_args.args, ("PUT", "https://rtc.live.cloudflare.com/v1/apps/app1/sessions/S-k-guest/renegotiate")
        )
        self.assertEqual(self.client_g.delete(f"{API}/groups/{self.group.pk}/voice").status_code, 204)
        self.assertEqual(call.call_args.kwargs["json"], {"tracks": [{"mid": "0"}], "force": True})
        self.assertFalse(VoiceSession.objects.filter(user=self.guest).exists())

    @mock.patch("trainer.voice.requests.request")
    def test_a_media_server_refusal_reaches_the_page_with_its_reason(self, call):
        call.return_value = _answer(400, {"errorCode": "invalid_request", "errorDescription": "bad SDP"})
        refused = self.join(self.client_g)
        self.assertEqual(refused.status_code, 502)
        self.assertIn("bad SDP", refused.json()["detail"])
        self.assertFalse(VoiceSession.objects.exists())

    def test_an_offer_or_a_list_too_long_is_refused(self):
        self.assertEqual(self.join(self.client_g, offer="v" * 100_001).status_code, 422)
        self.in_voice(self.guest, "k-guest")
        keys = [f"k{i}" for i in range(51)]
        self.assertEqual(
            self.post(self.client_g, f"/groups/{self.group.pk}/voice/pull", {"keys": keys}).status_code, 422
        )
