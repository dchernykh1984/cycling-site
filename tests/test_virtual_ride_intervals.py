"""Where a member's rides go (issue #471): Strava and intervals.icu, each connected or not, each with its box.

intervals.icu is connected with the member's own API key, checked with intervals.icu and kept sealed;
rides go there as they go to Strava. Every call to intervals.icu is a patched ``requests.request``.
"""

import json
import sys
from unittest import mock

import requests
from django.conf import settings
from django.contrib.messages import get_messages
from django.core import checks
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext
from django.views.debug import ExceptionReporter

from tests.test_virtual_ride_api import API, MemberClientMixin, _ride, _user
from tests.test_virtual_ride_strava import STRAVA_ON, _answer, _connect, _track
from trainer import intervals, secret_box, views
from trainer.models import IntervalsConnection, IntervalsUpload, RideTrack, StravaConnection, VirtualRide

KEY = "abc123-the-members-own-key"
OTHER_SITE_KEY = "b3RoZXItc2l0ZS1rZXktb3BlbnMtbm90aGluZy0zMmI="  # a valid key, but not the one the tests seal with
# the tests' own cache counts nothing; the tries a member is allowed need one that does
COUNTING_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tries"}}


def _connected(user, send_rides=True, athlete_id="i42"):
    return IntervalsConnection.objects.create(
        user=user, athlete_id=athlete_id, athlete_name="Anna R", api_key=secret_box.seal(KEY), send_rides=send_rides
    )


def _calls(call, method):
    return [c for c in call.call_args_list if c.args[0] == method]


def _page(status=200):
    """What a proxy in front of intervals.icu may answer instead of its data: a page."""
    response = mock.Mock(status_code=status, text="<html><body>One moment, please</body></html>")
    response.json.side_effect = requests.JSONDecodeError("Expecting value", response.text, 0)
    return response


class SecretBoxTests(TestCase):
    def test_a_sealed_key_opens_only_with_the_site_s_key(self):
        sealed = secret_box.seal(KEY)
        self.assertNotIn(KEY, sealed)
        self.assertEqual(secret_box.open_sealed(sealed), KEY)
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=OTHER_SITE_KEY):
            self.assertIsNone(secret_box.open_sealed(sealed))

    def test_without_a_usable_site_key_nothing_is_offered(self):
        for unusable in ("", "not-a-fernet-key"):
            with override_settings(INTEGRATIONS_ENCRYPTION_KEY=unusable):
                self.assertFalse(secret_box.available())
                self.assertFalse(intervals.available())
                self.assertIsNone(secret_box.open_sealed("anything"))
                with self.assertRaises(RuntimeError):
                    secret_box.seal(KEY)


def _startup_warnings():
    return [message.id for message in checks.run_checks() if message.id and message.id.startswith("trainer.")]


class StartupCheckTests(TestCase):
    def test_a_key_set_but_unusable_is_said_at_startup(self):
        self.assertEqual(_startup_warnings(), [])
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY="pasted-with-a-typo"):
            self.assertEqual(_startup_warnings(), ["trainer.W001"])
        # a Strava application without the key is said apart (trainer.W002), so none here, whatever .env holds
        no_strava = settings.SOCIALACCOUNT_PROVIDERS | {"strava": {"APP": {}}}
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY="", SOCIALACCOUNT_PROVIDERS=no_strava):
            self.assertEqual(_startup_warnings(), [], "no key is a site without intervals.icu, by choice")


class ErrorReportTests(TestCase):
    """A server error mails its report, with every frame's variables, to the admins: never with a key."""

    def setUp(self):
        self.user = _user("anna")

    def report_of(self, act, request=None):
        request = request or RequestFactory().post("/")
        try:
            act()
        except RuntimeError:
            return ExceptionReporter(request, *sys.exc_info()).get_traceback_html()
        self.fail("nothing went wrong")

    @mock.patch("trainer.intervals.requests.request")
    def test_a_failure_while_connecting_leaves_the_key_out(self, call):
        call.side_effect = RuntimeError("the library broke")  # deep down, where the key travels as auth
        self.assertNotIn(KEY, self.report_of(lambda: intervals.connect(self.user, KEY)))
        call.side_effect = None
        call.return_value = _answer(200, {"id": "i42"})
        with mock.patch.object(IntervalsConnection.objects, "update_or_create", side_effect=RuntimeError("db gone")):
            self.assertNotIn(KEY, self.report_of(lambda: intervals.connect(self.user, KEY)))

    @mock.patch("trainer.intervals.requests.request")
    def test_a_failure_in_the_profile_s_form_leaves_the_key_out(self, call):
        call.side_effect = RuntimeError("the library broke")
        request = RequestFactory().post("/", {"api_key": KEY})
        request.user = self.user
        report = self.report_of(lambda: views.intervals_connect(request), request)
        self.assertIn("api_key", report)
        self.assertNotIn(KEY, report)

    @mock.patch("trainer.intervals.requests.request")
    def test_a_failure_while_uploading_leaves_the_key_out(self, call):
        _connected(self.user)
        ride = VirtualRide.objects.create(user=self.user, route="center", duration_s=3, distance_m=16)
        RideTrack.objects.create(ride=ride, points=_track())
        call.side_effect = RuntimeError("the library broke")
        self.assertNotIn(KEY, self.report_of(lambda: intervals.upload(ride)))


class ConnectTests(TestCase):
    def setUp(self):
        self.user = _user("anna")

    @mock.patch("trainer.intervals.requests.request")
    def test_a_key_intervals_icu_accepts_is_kept_sealed_with_its_athlete(self, call):
        call.return_value = _answer(200, {"id": "i42", "name": "Anna R"})
        intervals.connect(self.user, f"  {KEY} ", send_rides=True)
        method, url = call.call_args.args
        self.assertEqual((method, url), ("GET", f"{intervals.API}/athlete/0"))
        self.assertEqual(call.call_args.kwargs["auth"], ("API_KEY", KEY))
        self.assertIn("UniversalBicycleTeam", call.call_args.kwargs["headers"]["User-Agent"])
        stored = IntervalsConnection.objects.get(user=self.user)
        self.assertEqual((stored.athlete_id, stored.athlete_name, stored.send_rides), ("i42", "Anna R", True))
        self.assertNotIn(KEY, stored.api_key)
        self.assertEqual(secret_box.open_sealed(stored.api_key), KEY)

    @mock.patch("trainer.intervals.requests.request")
    def test_a_refused_key_keeps_nothing(self, call):
        for status, verdict_on_the_key in ((401, True), (403, False)):
            call.return_value = _answer(status)
            with self.assertRaises(intervals.IntervalsError) as caught:
                intervals.connect(self.user, KEY)
            self.assertEqual(caught.exception.revoked, verdict_on_the_key, status)
        self.assertFalse(IntervalsConnection.objects.exists())

    @override_settings(CACHES=COUNTING_CACHE)
    @mock.patch("trainer.intervals.requests.request")
    def test_a_member_trying_key_after_key_is_held_back_before_intervals_icu_is_asked(self, call):
        call.return_value = _answer(401)
        for _ in range(5):
            with self.assertRaises(intervals.IntervalsError):
                intervals.connect(self.user, KEY)
        call.reset_mock()
        with self.assertRaises(intervals.IntervalsError) as caught:
            intervals.connect(self.user, KEY)
        self.assertIn("Too many tries", str(caught.exception))
        call.assert_not_called()
        # another member is not held back by this one
        call.return_value = _answer(200, {"id": "i9", "name": "Boris"})
        intervals.connect(_user("boris"), KEY)

    @mock.patch("trainer.intervals.requests.request")
    def test_an_answer_without_an_athlete_or_no_answer_keeps_nothing(self, call):
        for answer in (
            _answer(200, {"name": "nobody"}),
            _answer(500),
            _answer(429),
            _page(),
            requests.ConnectionError("down"),
        ):
            call.reset_mock(side_effect=True, return_value=True)
            if isinstance(answer, Exception):
                call.side_effect = answer
            else:
                call.return_value = answer
            with self.assertRaises(intervals.IntervalsError):
                intervals.connect(self.user, KEY)
        with self.assertRaises(intervals.IntervalsError):
            intervals.connect(self.user, "   ")
        self.assertFalse(IntervalsConnection.objects.exists())


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class SendingTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client_m = self.member(self.user)

    def save(self, **overrides):
        return self.post(self.client_m, "/rides", _ride(track=_track(), **overrides))

    @mock.patch("trainer.intervals.requests.request")
    def test_a_ride_goes_to_intervals_icu_when_its_box_is_on(self, call):
        _connected(self.user)
        call.side_effect = [_answer(201, {"id": "i9876", "activities": [{"id": "i9876"}]}), _answer(200)]
        saved = self.save()
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(
            saved.json()["intervals"],
            {"status": "done", "activity_url": "https://intervals.icu/activities/i9876", "error": ""},
        )
        ride = VirtualRide.objects.get()
        post = _calls(call, "POST")[0]
        self.assertEqual(post.args[1], f"{intervals.API}/athlete/i42/activities")
        self.assertEqual(post.kwargs["auth"], ("API_KEY", KEY))
        self.assertEqual(post.kwargs["params"]["external_id"], f"universalbicycle-virtual-ride-{ride.pk}")
        self.assertEqual(post.kwargs["params"]["name"], "Center loop")
        name, content, _type = post.kwargs["files"]["file"]
        self.assertTrue(name.endswith(".tcx"))
        self.assertTrue(content.startswith(b"<?xml"), "sent unpacked: intervals.icu does not document gzip")
        self.assertIn(b"<tpx:Watts>200</tpx:Watts>", content, "the power of every point goes too")
        put = _calls(call, "PUT")[0]
        self.assertEqual((put.args[1], put.kwargs["json"]["type"]), (f"{intervals.API}/activity/i9876", "VirtualRide"))
        self.assertLess(put.kwargs["timeout"], post.kwargs["timeout"], "the mark holds the save less than the upload")
        self.assertEqual(ride.intervals.status, IntervalsUpload.Status.DONE)

    @mock.patch("trainer.intervals.requests.request")
    def test_a_refused_virtual_mark_still_leaves_the_ride_there(self, call):
        _connected(self.user)
        call.side_effect = [_answer(200, {"id": "i9876"}), _answer(404)]
        self.assertEqual(self.save().json()["intervals"]["status"], "done")

    @mock.patch("trainer.strava.requests.request")
    @mock.patch("trainer.intervals.requests.request")
    def test_with_the_boxes_off_nothing_is_sent_on_its_own(self, to_intervals, to_strava):
        _connected(self.user, send_rides=False)
        strava = _connect(self.user)
        strava.send_rides = False
        strava.save()
        saved = self.save()
        self.assertEqual((saved.json()["strava"], saved.json()["intervals"]), (None, None))
        to_intervals.assert_not_called()
        to_strava.assert_not_called()

    def test_a_strava_connection_sends_until_its_box_is_turned_off(self):
        self.assertTrue(_connect(self.user).send_rides)

    @mock.patch("trainer.intervals.requests.request")
    def test_demo_rides_and_rides_without_a_track_stay_here(self, call):
        _connected(self.user)
        self.assertIsNone(self.save(power_source="demo").json()["intervals"])
        self.assertIsNone(self.post(self.client_m, "/rides", _ride()).json()["intervals"])
        call.assert_not_called()

    @mock.patch("trainer.intervals.requests.request")
    def test_a_403_fails_the_upload_and_keeps_the_connection(self, call):
        # the proxy in front of intervals.icu answers 403 when it turns the site's address away
        _connected(self.user)
        call.return_value = _answer(403, text="<html>Sorry, you have been blocked</html>")
        body = self.save().json()["intervals"]
        self.assertEqual(body["status"], "failed")
        self.assertTrue(IntervalsConnection.objects.filter(user=self.user).exists())

    @mock.patch("trainer.intervals.requests.request")
    def test_a_key_intervals_icu_no_longer_takes_drops_the_connection(self, call):
        _connected(self.user)
        call.return_value = _answer(401)
        body = self.save().json()["intervals"]
        self.assertEqual(body["status"], "failed")
        self.assertIn("does not accept this key", body["error"])
        self.assertFalse(IntervalsConnection.objects.exists())

    @mock.patch("trainer.intervals.requests.request")
    def test_intervals_icu_out_of_reach_fails_the_upload_and_keeps_the_connection(self, call):
        _connected(self.user)
        call.side_effect = requests.Timeout("slow")
        body = self.save().json()["intervals"]
        self.assertEqual(body["status"], "failed")
        self.assertIn("could not be reached", body["error"])
        self.assertTrue(IntervalsConnection.objects.exists())

    @mock.patch("trainer.intervals.requests.request")
    def test_a_key_this_site_can_no_longer_open_drops_the_connection(self, call):
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=OTHER_SITE_KEY):
            _connected(self.user)
        body = self.save().json()["intervals"]
        self.assertEqual(body["status"], "failed")
        self.assertIn("connect intervals.icu again", body["error"])
        self.assertFalse(IntervalsConnection.objects.exists())
        call.assert_not_called()

    @mock.patch("trainer.intervals.requests.request")
    def test_send_again_after_a_failure_and_never_twice(self, call):
        _connected(self.user)
        call.side_effect = requests.Timeout("slow")
        ride_id = self.save().json()["ride"]["id"]
        call.side_effect = [_answer(200, {"id": "i5"}), _answer(200)]
        again = self.post(self.client_m, f"/rides/{ride_id}/intervals")
        self.assertEqual(again.json()["status"], "done")
        call.reset_mock()
        self.assertEqual(self.post(self.client_m, f"/rides/{ride_id}/intervals").json()["status"], "done")
        call.assert_not_called()
        self.assertEqual(
            self.client_m.get(f"{API}/rides/{ride_id}/intervals").json()["activity_url"],
            "https://intervals.icu/activities/i5",
        )

    @mock.patch("trainer.intervals.requests.request")
    def test_send_again_needs_the_connection_and_a_ride_with_its_track(self, call):
        demo = self.save(power_source="demo").json()["ride"]["id"]
        self.assertEqual(self.post(self.client_m, f"/rides/{demo}/intervals").status_code, 409)
        _connected(self.user, send_rides=False)
        self.assertEqual(self.post(self.client_m, f"/rides/{demo}/intervals").status_code, 409)
        other = _user("boris")
        theirs = VirtualRide.objects.create(user=other, route="center", duration_s=10, distance_m=10)
        self.assertEqual(self.post(self.client_m, f"/rides/{theirs.pk}/intervals").status_code, 404)
        self.assertEqual(self.client_m.get(f"{API}/rides/{theirs.pk}/intervals").status_code, 404)
        call.assert_not_called()


class UploadAnswerTests(TestCase):
    """The answers an upload can meet, each recorded rather than raised."""

    def setUp(self):
        self.user = _user("anna")
        self.ride = VirtualRide.objects.create(
            user=self.user, route="center", route_name="Center loop", duration_s=3, distance_m=16
        )
        RideTrack.objects.create(ride=self.ride, points=_track())

    @mock.patch("trainer.intervals.requests.request")
    def test_without_a_connection_or_a_track_nothing_is_sent(self, call):
        self.assertIn("Not connected", intervals.upload(self.ride).error)
        _connected(self.user)
        RideTrack.objects.all().delete()
        self.assertIn("no track", intervals.upload(self.ride).error)
        call.assert_not_called()

    @mock.patch("trainer.intervals.requests.request")
    def test_a_refusal_or_an_answer_naming_no_activity_fails_the_upload(self, call):
        _connected(self.user)
        call.return_value = _answer(500, text="server error")
        self.assertEqual(
            (intervals.upload(self.ride).status, intervals.upload(self.ride).error), ("failed", "server error")
        )
        call.return_value = _answer(200, {"activities": []})
        self.assertIn("named no activity", intervals.upload(self.ride).error)

    @mock.patch("trainer.intervals.requests.request")
    def test_a_page_or_other_data_instead_of_an_activity_fails_the_upload(self, call):
        _connected(self.user)
        for answer in (_page(), _answer(201, ["i3"])):
            call.reset_mock(side_effect=True, return_value=True)
            call.return_value = answer
            sent = intervals.upload(self.ride)
            self.assertEqual(sent.status, IntervalsUpload.Status.FAILED)
            self.assertIn("without its usual data", sent.error)

    @mock.patch("trainer.intervals.requests.request")
    def test_a_virtual_mark_refused_outright_is_let_go(self, call):
        _connected(self.user)
        call.side_effect = [_answer(200, {"id": "i3"}), requests.ConnectionError("gone")]
        self.assertEqual(intervals.upload(self.ride).status, IntervalsUpload.Status.DONE)


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class ServicesApiTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client_m = self.member(self.user)

    def patch(self, path, data):
        return self.client_m.patch(f"{API}{path}", data=json.dumps(data), content_type="application/json")

    def test_a_member_reads_where_their_rides_go_and_never_the_key(self):
        _connected(self.user, send_rides=False)
        body = self.client_m.get(f"{API}/services").json()
        self.assertEqual(
            body["intervals"], {"available": True, "connected": True, "athlete": "Anna R", "send_rides": False}
        )
        self.assertEqual(body["strava"], {"available": True, "connected": False, "athlete": "", "send_rides": False})
        self.assertTrue(body["strava_connect_url"])
        for path in ("/services", "/me"):
            text = self.client_m.get(f"{API}{path}").content.decode()
            self.assertNotIn(KEY, text)
            self.assertNotIn(IntervalsConnection.objects.get().api_key, text)

    def test_the_trainer_page_is_told_each_service_s_state(self):
        _connected(self.user)
        me = self.client_m.get(f"{API}/me").json()
        self.assertEqual(
            (me["intervals_available"], me["intervals_connected"], me["intervals_send"], me["intervals_athlete"]),
            (True, True, True, "Anna R"),
        )
        self.assertEqual((me["strava_connected"], me["strava_send"]), (False, False))

    def test_a_box_turns_on_and_off_only_for_a_connected_service(self):
        self.assertEqual(self.patch("/services/strava", {"send_rides": False}).status_code, 409)
        self.assertEqual(self.patch("/services/intervals", {"send_rides": True}).status_code, 409)
        _connect(self.user)
        _connected(self.user, send_rides=False)
        self.assertFalse(self.patch("/services/strava", {"send_rides": False}).json()["strava"]["send_rides"])
        self.assertTrue(self.patch("/services/intervals", {"send_rides": True}).json()["intervals"]["send_rides"])
        self.assertFalse(StravaConnection.objects.get().send_rides)
        self.assertTrue(IntervalsConnection.objects.get().send_rides)

    @mock.patch("trainer.intervals.requests.request")
    def test_intervals_icu_is_connected_with_a_key_and_disconnected(self, call):
        call.return_value = _answer(200, {"id": "i42", "name": "Anna R"})
        made = self.post(self.client_m, "/services/intervals", {"api_key": KEY, "send_rides": True})
        self.assertEqual(made.status_code, 201)
        self.assertEqual(made.json()["intervals"]["send_rides"], True)
        self.assertNotIn(KEY, made.content.decode())
        gone = self.client_m.delete(f"{API}/services/intervals")
        self.assertEqual(gone.status_code, 204)
        self.assertFalse(IntervalsConnection.objects.exists())

    @mock.patch("trainer.intervals.requests.request")
    def test_a_refused_key_is_answered_with_the_reason(self, call):
        call.return_value = _answer(401)
        refused = self.post(self.client_m, "/services/intervals", {"api_key": KEY})
        self.assertEqual(refused.status_code, 422)
        self.assertIn("does not accept this key", refused.json()["detail"])
        self.assertFalse(IntervalsConnection.objects.exists())

    @override_settings(CACHES=COUNTING_CACHE)
    @mock.patch("trainer.intervals.requests.request")
    def test_key_after_key_is_answered_too_many_requests(self, call):
        call.return_value = _answer(401)
        for _ in range(5):
            self.assertEqual(self.post(self.client_m, "/services/intervals", {"api_key": KEY}).status_code, 422)
        self.assertEqual(self.post(self.client_m, "/services/intervals", {"api_key": KEY}).status_code, 429)

    def test_the_key_is_bounded_and_needed(self):
        for bad in ({"api_key": ""}, {"api_key": "k" * 201}, {}):
            self.assertEqual(self.post(self.client_m, "/services/intervals", bad).status_code, 422)

    @override_settings(INTEGRATIONS_ENCRYPTION_KEY="")
    def test_a_site_that_cannot_keep_the_key_offers_no_intervals_icu(self):
        self.assertEqual(self.post(self.client_m, "/services/intervals", {"api_key": KEY}).status_code, 409)
        self.assertFalse(self.client_m.get(f"{API}/services").json()["intervals"]["available"])

    def test_a_guest_reaches_none_of_it(self):
        self.assertEqual(self.client.get(f"{API}/services").status_code, 401)
        for method, path in (
            ("patch", "/services/strava"),
            ("post", "/services/intervals"),
            ("delete", "/services/intervals"),
        ):
            answer = getattr(self.client, method)(f"{API}{path}", data="{}", content_type="application/json")
            self.assertEqual(answer.status_code, 401, (method, path))


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class ProfileTests(TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client.force_login(self.user)

    def card(self):
        return self.client.get(reverse("account_profile")).content.decode()

    def test_the_card_lists_both_services_with_their_state(self):
        html = self.card()
        self.assertIn('id="virtual-rides-services"', html)
        self.assertIn('id="virtual-rides-strava"', html)
        self.assertIn('id="intervals-key"', html)
        # a password manager would fill the member's own password into a password field
        self.assertNotIn('type="password" name="api_key"', html)
        self.assertIn('name="api_key" id="intervals-key" required maxlength="200" autocomplete="off"', html)
        _connect(self.user)
        _connected(self.user, send_rides=False)
        html = self.card()
        self.assertIn('id="send-strava" checked', html)
        self.assertIn('id="send-intervals">', html)
        self.assertIn("Anna R", html)
        self.assertNotIn('id="intervals-key"', html)
        self.assertNotIn(KEY, html)

    @override_settings(INTEGRATIONS_ENCRYPTION_KEY="")
    def test_without_the_site_key_intervals_icu_is_not_offered(self):
        self.assertNotIn('id="virtual-rides-intervals"', self.card())
        self.assertEqual(self.client.post(reverse("virtual_ride_intervals_connect"), {"api_key": KEY}).status_code, 404)

    def test_the_boxes_save_and_say_so(self):
        _connect(self.user)
        answer = self.client.post(reverse("virtual_ride_service_sending", args=["strava"]), follow=True)
        self.assertRedirects(
            answer, reverse("account_profile") + "#virtual-rides-services", fetch_redirect_response=False
        )
        self.assertFalse(StravaConnection.objects.get().send_rides)
        self.client.post(reverse("virtual_ride_service_sending", args=["strava"]), {"send_rides": "on"})
        self.assertTrue(StravaConnection.objects.get().send_rides)
        self.assertEqual(self.client.post(reverse("virtual_ride_service_sending", args=["garmin"])).status_code, 404)

    @mock.patch("trainer.intervals.requests.request")
    def test_connecting_and_disconnecting_from_the_profile(self, call):
        call.return_value = _answer(401)
        self.client.post(reverse("virtual_ride_intervals_connect"), {"api_key": KEY})
        self.assertFalse(IntervalsConnection.objects.exists())
        call.return_value = _answer(200, {"id": "i42", "name": "Anna R"})
        self.client.post(reverse("virtual_ride_intervals_connect"), {"api_key": KEY, "send_rides": "on"})
        self.assertTrue(IntervalsConnection.objects.get().send_rides)
        self.client.post(reverse("virtual_ride_intervals_disconnect"))
        self.assertFalse(IntervalsConnection.objects.exists())

    def told(self, key):
        """What the member reads after giving ``key`` on the Russian page: the newest message."""
        with translation.override("ru"):
            sent = self.client.post(reverse("virtual_ride_intervals_connect"), {"api_key": key})
            return [str(message) for message in get_messages(sent.wsgi_request)][-1]

    def said(self, text):
        with translation.override("ru"):
            translated = gettext(text)
        self.assertNotEqual(translated, text, "the Russian catalogue lacks it")
        return translated

    @mock.patch("trainer.intervals.requests.request")
    def test_a_key_not_connected_is_told_in_the_member_s_language(self, call):
        refused = "intervals.icu does not accept this key. Check it and try again."
        call.return_value = _answer(401)
        self.assertEqual(self.told(KEY), self.said(refused))
        self.assertEqual(self.told("   "), self.said(refused))
        call.side_effect = requests.ConnectionError("down")
        self.assertEqual(
            self.told(KEY), self.said("intervals.icu could not check the key just now. Try connecting again later.")
        )

    @override_settings(CACHES=COUNTING_CACHE)
    @mock.patch("trainer.intervals.requests.request")
    def test_key_after_key_is_told_to_wait(self, call):
        call.return_value = _answer(401)
        for _ in range(5):
            self.told(KEY)
        self.assertEqual(
            self.told(KEY), self.said("Too many keys tried in a row: wait a few minutes, then give yours again.")
        )

    def test_a_recent_ride_links_to_its_activity_there(self):
        ride = VirtualRide.objects.create(
            user=self.user, route="center", route_name="Center loop", duration_s=60, distance_m=500
        )
        IntervalsUpload.objects.create(ride=ride, status=IntervalsUpload.Status.DONE, activity_id="i77")
        self.assertIn('href="https://intervals.icu/activities/i77"', self.card())

    def test_the_forms_need_a_signed_in_member_and_a_post(self):
        self.assertEqual(self.client.get(reverse("virtual_ride_intervals_disconnect")).status_code, 405)
        self.client.logout()
        answer = self.client.post(reverse("virtual_ride_intervals_connect"), {"api_key": KEY})
        self.assertEqual(answer.status_code, 302)
        self.assertIn(reverse("account_login"), answer["Location"])
