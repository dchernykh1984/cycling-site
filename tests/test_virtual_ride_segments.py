"""The virtual ride's live segments: the member's starred Strava segments and their own efforts on them."""

from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from tests.test_virtual_ride_api import API, MemberClientMixin, _user
from tests.test_virtual_ride_strava import STRAVA_ON, _answer, _connect
from trainer import strava
from trainer.models import StravaConnection

READS_SEGMENTS = f"{strava.SCOPE},{strava.SEGMENTS_SCOPE}"


def _starred():
    return [
        {
            "id": 101,
            "name": "Dulati climb",
            "activity_type": "Ride",
            "distance": 1200.5,
            "average_grade": 4.2,
            "start_latlng": [43.20, 76.90],
            "end_latlng": [43.19, 76.91],
            "athlete_pr_effort": {"pr_elapsed_time": 245},
        },
        {"id": 102, "name": "Park run", "activity_type": "Run", "start_latlng": [43.2, 76.9], "end_latlng": [1, 2]},
        {"id": 103, "name": "No line", "activity_type": "Ride", "start_latlng": [], "end_latlng": []},
    ]


def _line():
    return {
        "latlng": {"data": [[43.2, 76.9], [43.195, 76.905], [43.19, 76.91]]},
        "distance": {"data": [0.0, 600.0, 1200.5]},
        "altitude": {"data": [900.0, 925.0, 950.0]},
    }


def _efforts():
    return [
        {"id": 7, "elapsed_time": 260, "start_date_local": "2026-05-01T08:00:00Z"},
        {"id": 8, "elapsed_time": 245, "start_date_local": "2026-06-02T08:00:00Z"},
        {"id": 9, "elapsed_time": 300},
    ]


def _effort_streams():
    # an effort's streams run on from its activity's: its distance and its clock start where the activity had them
    return {"distance": {"data": [5000.0, 5600.0, 6200.5]}, "time": {"data": [900, 1020, 1145]}}


def _strava(url, params):
    """Strava as the tests' member has it: a subscriber's answers to each read."""
    answers = {
        strava.STARRED_URL: _starred(),
        strava.SEGMENT_STREAMS_URL.format(101): _line(),
        strava.EFFORTS_URL: _efforts(),
        strava.EFFORT_STREAMS_URL.format(8): _effort_streams(),
    }
    return _answer(200, answers[url]) if url in answers else _answer(404)


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class SegmentsGrantTests(TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client.force_login(self.user)

    def start(self, **query):
        response = self.client.get(reverse("virtual_ride_strava_connect"), query)
        return parse_qs(urlsplit(response["Location"]).query)

    def back(self, state, scope):
        return self.client.get(reverse("virtual_ride_strava_callback"), {"state": state, "code": "c", "scope": scope})

    def tokens(self, post):
        later = int((timezone.now() + timedelta(hours=6)).timestamp())
        post.return_value = _answer(200, {"access_token": "a", "refresh_token": "r", "expires_at": later})

    def test_the_live_segments_ask_strava_to_read_the_member_s_efforts_too(self):
        self.assertEqual(self.start(segments="1")["scope"], [READS_SEGMENTS])

    @mock.patch("trainer.strava.requests.post")
    def test_coming_back_with_both_permissions_keeps_them_and_the_page_learns_it(self, post):
        self.tokens(post)
        self.back(self.start(segments="1")["state"][0], READS_SEGMENTS)
        self.assertEqual(StravaConnection.objects.get(user=self.user).scope, READS_SEGMENTS)
        me = self.client.get(f"{API}/me").json()
        self.assertTrue(me["strava_segments"])
        self.assertEqual(me["strava_segments_url"], reverse("virtual_ride_strava_connect") + "?segments=1")

    @mock.patch("trainer.strava.requests.post")
    def test_a_member_who_allowed_the_segments_is_asked_for_them_again(self, post):
        self.tokens(post)
        self.back(self.start(segments="1")["state"][0], READS_SEGMENTS)
        self.assertEqual(self.start()["scope"], [READS_SEGMENTS])

    @mock.patch("trainer.strava.requests.post")
    def test_uploads_allowed_without_the_segments_connect_and_say_what_is_missing(self, post):
        self.tokens(post)
        page = self.back(self.start(segments="1")["state"][0], strava.SCOPE)
        self.assertFalse(strava.reads_segments(StravaConnection.objects.get(user=self.user)))
        said = gettext(
            "Strava is connected for your rides, but did not allow reading your efforts on segments, so the "
            "virtual ride has no live segments. Connect again and keep that permission on."
        )
        self.assertEqual([str(m) for m in page.wsgi_request._messages], [said])
        self.assertFalse(self.client.get(f"{API}/me").json()["strava_segments"])

    @mock.patch("trainer.strava.requests.post")
    def test_segments_without_the_upload_permission_connect_nothing_and_say_why(self, post):
        page = self.back(self.start(segments="1")["state"][0], f"read,{strava.SEGMENTS_SCOPE}")
        said = gettext(
            "Strava did not allow uploading activities: the live segments come with the Strava connection "
            "for your rides, which needs it. Connect again and keep both permissions on."
        )
        self.assertEqual([str(m) for m in page.wsgi_request._messages], [said])
        self.assertFalse(StravaConnection.objects.exists())
        post.assert_not_called()


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class SegmentsApiTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client_m = self.member(self.user)
        self.connection = _connect(self.user)
        self.connection.scope = READS_SEGMENTS
        self.connection.save()

    def test_without_the_permission_nothing_is_read_from_strava(self):
        self.connection.scope = strava.SCOPE
        self.connection.save()
        with mock.patch("trainer.strava.requests.request") as call:
            self.assertEqual(self.client_m.get(f"{API}/strava/segments").status_code, 409)
            self.assertEqual(self.client_m.get(f"{API}/strava/segments/101").status_code, 409)
        call.assert_not_called()

    @mock.patch("trainer.strava.requests.request")
    def test_the_member_s_starred_rides_come_with_their_best_time(self, call):
        call.side_effect = lambda method, url, **kw: _strava(url, kw.get("params"))
        listed = self.client_m.get(f"{API}/strava/segments").json()
        self.assertEqual(
            listed,
            [
                {
                    "id": 101,
                    "name": "Dulati climb",
                    "distance_m": 1200.5,
                    "average_grade": 4.2,
                    "start": [43.2, 76.9],
                    "end": [43.19, 76.91],
                    "pr_s": 245.0,
                }
            ],
        )
        self.assertEqual(call.call_args.kwargs["params"], {"per_page": strava.STARRED_PAGE})

    @mock.patch("trainer.strava.requests.request")
    def test_a_segment_comes_with_its_line_the_member_s_times_and_their_best_effort_s_pace(self, call):
        call.side_effect = lambda method, url, **kw: _strava(url, kw.get("params"))
        seg = self.client_m.get(f"{API}/strava/segments/101").json()
        self.assertEqual(seg["points"][-1], [43.19, 76.91, 950.0, 1200.5])
        self.assertEqual(seg["efforts"], [245.0, 260.0, 300.0])
        # the best effort's pace from its own start, not its activity's
        self.assertEqual(
            seg["best"], {"elapsed_s": 245.0, "date": "2026-06-02", "times": [[0, 0], [600, 120], [1200.5, 245]]}
        )

    @mock.patch("trainer.strava.requests.request")
    def test_without_strava_s_subscription_the_segment_comes_without_efforts(self, call):
        def no_subscription(method, url, **kw):
            return _answer(402) if url == strava.EFFORTS_URL else _strava(url, kw.get("params"))

        call.side_effect = no_subscription
        seg = self.client_m.get(f"{API}/strava/segments/101").json()
        self.assertEqual((seg["efforts"], seg["best"], len(seg["points"])), (None, None, 3))

    @mock.patch("trainer.strava.requests.request")
    def test_a_best_effort_without_its_streams_keeps_its_time(self, call):
        def no_streams(method, url, **kw):
            return _answer(404) if url == strava.EFFORT_STREAMS_URL.format(8) else _strava(url, kw.get("params"))

        call.side_effect = no_streams
        best = self.client_m.get(f"{API}/strava/segments/101").json()["best"]
        self.assertEqual((best["elapsed_s"], best["times"]), (245.0, []))

    @mock.patch("trainer.strava.requests.request")
    def test_a_long_line_is_thinned_to_what_the_page_draws_with_its_end_kept(self, call):
        n = 1000
        line = {
            "latlng": {"data": [[43.2 + i * 1e-5, 76.9] for i in range(n)]},
            "distance": {"data": [float(i) for i in range(n)]},
            "altitude": {"data": [900.0] * n},
        }
        call.side_effect = lambda method, url, **kw: (
            _answer(200, line) if url == strava.SEGMENT_STREAMS_URL.format(101) else _answer(402)
        )
        points = self.client_m.get(f"{API}/strava/segments/101").json()["points"]
        self.assertEqual((len(points), points[0][3], points[-1][3]), (strava.SEGMENT_POINTS, 0, n - 1))

    @mock.patch("trainer.strava.requests.request")
    def test_a_grant_strava_refused_is_forgotten(self, call):
        call.return_value = _answer(401)
        with mock.patch("trainer.strava.requests.post"):
            self.assertEqual(self.client_m.get(f"{API}/strava/segments").status_code, 409)
        self.assertFalse(StravaConnection.objects.exists())

    @mock.patch("trainer.strava.requests.request")
    def test_strava_s_trouble_is_said_and_the_grant_kept(self, call):
        call.return_value = _answer(429)
        answer = self.client_m.get(f"{API}/strava/segments")
        self.assertEqual((answer.status_code, answer.json()["detail"]), (502, "Strava answered 429"))
        self.assertTrue(StravaConnection.objects.exists())

    def test_a_guest_reads_nothing(self):
        self.assertEqual(self.client.get(f"{API}/strava/segments").status_code, 401)
