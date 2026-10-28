"""Virtual rides sent to Strava as Virtual Ride activities: the grant, the track, the upload, the profile."""

import gzip
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET

import requests
from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override as translation_override

from accounts.models import User
from tests.language_urls import in_language
from tests.test_virtual_ride_api import API, MemberClientMixin, _ride, _user
from trainer import strava
from trainer.models import RideTrack, StravaConnection, StravaUpload, VirtualRide

STRAVA_ON = {
    **settings.SOCIALACCOUNT_PROVIDERS,
    "strava": {**settings.SOCIALACCOUNT_PROVIDERS["strava"], "APP": {"client_id": "65938", "secret": "s3cret"}},
}
TCX = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"
TPX = "{http://www.garmin.com/xmlschemas/ActivityExtension/v2}"


def _track(n=3):
    """A few seconds along the central loop: [t, lat, lon, ele, distance, speed, power, cadence, pulse]."""
    return [
        [i, 43.2402 + i * 0.0001, 76.9290 + i * 0.0001, 832 + i, i * 8.0, 8.0, 200 + i, 88, 0 if i else 140]
        for i in range(n)
    ]


def _answer(status, body=None, text=""):
    response = mock.Mock(status_code=status, text=text)
    response.json.return_value = body or {}
    return response


def _connect(user, expires_in=timedelta(hours=5)):
    return StravaConnection.objects.create(
        user=user,
        athlete_id=7,
        athlete_name="Anna R",
        access_token="access",
        refresh_token="refresh",
        expires_at=timezone.now() + expires_in,
    )


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class StravaUploadTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client_m = self.member(self.user)

    def save(self, **overrides):
        return self.post(self.client_m, "/rides", _ride(track=_track(), **overrides))

    @mock.patch("trainer.strava.requests.request")
    def test_a_connected_member_s_ride_goes_to_strava_as_a_virtual_ride(self, call):
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "991", "status": "Your activity is still being processed."})
        saved = self.save()
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()["strava"]["status"], "processing")
        method, url = call.call_args.args
        sent = call.call_args.kwargs
        self.assertEqual((method, url), ("POST", strava.UPLOADS_URL))
        self.assertEqual(sent["data"]["sport_type"], "VirtualRide")
        self.assertEqual(sent["data"]["data_type"], "tcx.gz")
        self.assertEqual(sent["headers"]["Authorization"], "Bearer access")
        ride = VirtualRide.objects.get()
        self.assertEqual(sent["data"]["external_id"], f"universalbicycle-virtual-ride-{ride.pk}")
        self.assertEqual(ride.track.points, _track())
        self.assertEqual(ride.strava.upload_id, "991")

    @mock.patch("trainer.strava.requests.request")
    def test_demo_rides_and_members_without_strava_send_nothing(self, call):
        self.assertIsNone(self.save().json()["strava"])  # not connected: the track is kept for later
        self.assertEqual(RideTrack.objects.count(), 1)
        _connect(self.user)
        self.assertIsNone(self.save(power_source="demo").json()["strava"])
        call.assert_not_called()

    def test_a_track_point_out_of_its_bounds_or_shape_is_refused(self):
        for bad in (
            [[0, 95, 76.9, 800, 0, 8, 200, 88, 140]],
            [[0, 43.2, 76.9, 800]],
            [[0, 43.2, 76.9, 800, 0, 8, 5000, 88, 140]],
        ):
            self.assertEqual(self.post(self.client_m, "/rides", _ride(track=bad)).status_code, 422, bad)
        too_long = [[0, 43.2, 76.9, 800, 0, 8, 200, 88, 140]] * (6 * 3600 + 1)
        self.assertEqual(self.post(self.client_m, "/rides", _ride(track=too_long)).status_code, 422)

    @mock.patch("trainer.strava.requests.post")
    @mock.patch("trainer.strava.requests.request")
    def test_an_expired_token_is_refreshed_before_the_upload(self, call, post):
        connection = _connect(self.user, expires_in=-timedelta(minutes=5))
        later = int((timezone.now() + timedelta(hours=6)).timestamp())
        post.return_value = _answer(200, {"access_token": "new", "refresh_token": "next", "expires_at": later})
        call.return_value = _answer(201, {"id_str": "5"})
        self.save()
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(call.call_args.kwargs["headers"]["Authorization"], "Bearer new")
        connection.refresh_from_db()
        self.assertEqual((connection.access_token, connection.refresh_token), ("new", "next"))

    @mock.patch("trainer.strava.requests.request")
    def test_a_grant_revoked_at_strava_is_forgotten_and_the_ride_says_why(self, call):
        _connect(self.user)
        call.return_value = _answer(401)
        self.assertEqual(self.save().json()["strava"]["status"], "failed")
        self.assertFalse(StravaConnection.objects.exists())

    @mock.patch("trainer.strava.requests.request")
    def test_the_status_turns_into_a_link_to_the_activity(self, call):
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "991"})
        ride_id = self.save().json()["ride"]["id"]
        call.return_value = _answer(200, {"id_str": "991", "activity_id": 123456789012})
        status = self.client_m.get(f"{API}/rides/{ride_id}/strava").json()
        self.assertEqual(
            status, {"status": "done", "activity_url": "https://www.strava.com/activities/123456789012", "error": ""}
        )
        self.assertEqual(call.call_args.args, ("GET", f"{strava.UPLOADS_URL}/991"))

    @mock.patch("trainer.strava.requests.request")
    def test_strava_s_error_is_kept_without_its_markup(self, call):
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "3", "error": "<b>Improperly formatted</b> data"})
        self.assertEqual(
            self.save().json()["strava"], {"status": "failed", "activity_url": "", "error": "Improperly formatted data"}
        )

    @mock.patch("trainer.strava.requests.request")
    def test_a_ride_strava_already_has_is_linked_to_its_activity_not_failed(self, call):
        _connect(self.user)
        duplicate = "virtual-ride-1.tcx.gz duplicate of <a href='/activities/4242'>Central loop</a>"
        call.return_value = _answer(201, {"id_str": "3", "error": duplicate})
        sent = self.save().json()["strava"]
        self.assertEqual((sent["status"], sent["activity_url"]), ("done", "https://www.strava.com/activities/4242"))

    @mock.patch("trainer.strava.requests.request")
    def test_a_ride_is_sent_again_on_request_but_only_with_a_track_and_a_grant(self, call):
        ride_id = self.save().json()["ride"]["id"]
        self.assertEqual(self.post(self.client_m, f"/rides/{ride_id}/strava").status_code, 409)  # not connected
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "8"})
        self.assertEqual(self.post(self.client_m, f"/rides/{ride_id}/strava").json()["status"], "processing")
        bare = self.post(self.client_m, "/rides", _ride()).json()["ride"]["id"]
        self.assertEqual(self.post(self.client_m, f"/rides/{bare}/strava").status_code, 409)  # no track
        other = self.member(_user("boris"))
        self.assertEqual(self.post(other, f"/rides/{ride_id}/strava").status_code, 404)

    @mock.patch("trainer.strava.requests.request")
    def test_a_slow_strava_fails_the_upload_and_keeps_the_ride(self, call):
        _connect(self.user)
        call.side_effect = requests.Timeout()
        saved = self.save()
        self.assertEqual((saved.status_code, saved.json()["strava"]["status"]), (201, "failed"))
        self.assertLessEqual(call.call_args.kwargs["timeout"], 10)  # a request thread is never held long

    @mock.patch("trainer.strava.requests.request")
    def test_a_ride_already_on_strava_keeps_its_activity_when_sent_again(self, call):
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "8", "activity_id": 77})
        ride_id = self.save().json()["ride"]["id"]
        again = self.post(self.client_m, f"/rides/{ride_id}/strava").json()
        self.assertEqual(again["activity_url"], "https://www.strava.com/activities/77")
        self.assertEqual(call.call_count, 1)  # nothing sent twice

    @mock.patch("trainer.strava.requests.post")
    def test_deleting_an_account_revokes_its_strava_grant_too(self, post):
        _connect(self.user)
        self.user.delete()
        self.assertEqual(post.call_args.args, (strava.DEAUTHORIZE_URL,))
        self.assertEqual(post.call_args.kwargs["data"], {"access_token": "access"})

    @mock.patch("trainer.strava.requests.post")
    @mock.patch("trainer.strava.requests.request")
    def test_a_grant_strava_refused_is_not_revoked_again(self, call, post):
        _connect(self.user)
        call.return_value = _answer(401)
        self.save()
        post.assert_not_called()

    @mock.patch("trainer.strava.requests.post")
    def test_turning_it_off_revokes_the_grant_and_forgets_the_tokens(self, post):
        _connect(self.user)
        self.assertEqual(self.client_m.delete(f"{API}/strava").status_code, 204)
        self.assertEqual(post.call_args.args, (strava.DEAUTHORIZE_URL,))
        self.assertFalse(StravaConnection.objects.exists())

    def test_the_page_learns_whether_strava_is_on_and_where_to_turn_it_on(self):
        me = self.client_m.get(f"{API}/me").json()
        self.assertEqual((me["strava_available"], me["strava_connected"]), (True, False))
        self.assertEqual(me["strava_connect_url"], reverse("virtual_ride_strava_connect"))
        _connect(self.user)
        me = self.client_m.get(f"{API}/me").json()
        self.assertEqual((me["strava_connected"], me["strava_athlete"]), (True, "Anna R"))

    def test_without_a_strava_application_nothing_is_offered(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS=settings.SOCIALACCOUNT_PROVIDERS | {"strava": {"APP": {}}}):
            me = self.client_m.get(f"{API}/me").json()
            self.assertEqual((me["strava_available"], me["strava_connect_url"]), (False, ""))
            self.assertEqual(self.client_m.get(reverse("virtual_ride_strava_connect")).status_code, 404)


class StravaFileTests(TestCase):
    def test_the_file_carries_the_route_s_places_power_and_pulse_from_the_ride_s_start(self):
        user = _user("anna")
        ride = VirtualRide.objects.create(user=user, route="center", duration_s=2, distance_m=16, max_speed_kmh=30)
        root = ET.fromstring(gzip.decompress(strava.tcx(ride, _track())))  # noqa: S314 -- the site's own file
        activity = root.find(f"{TCX}Activities/{TCX}Activity")
        self.assertEqual(activity.get("Sport"), "Biking")
        points = activity.findall(f"{TCX}Lap/{TCX}Track/{TCX}Trackpoint")
        self.assertEqual(len(points), 3)
        start = (ride.finished_at - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(points[0].findtext(f"{TCX}Time"), start)
        self.assertEqual(points[0].findtext(f"{TCX}Position/{TCX}LatitudeDegrees"), "43.240200")
        self.assertEqual(points[0].findtext(f"{TCX}HeartRateBpm/{TCX}Value"), "140")
        self.assertIsNone(points[1].find(f"{TCX}HeartRateBpm"))  # no pulse, no element
        self.assertEqual(points[2].findtext(f"{TCX}Extensions/{TPX}TPX/{TPX}Watts"), "202")


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class StravaGrantTests(TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client.force_login(self.user)

    def start(self, **query):
        response = self.client.get(reverse("virtual_ride_strava_connect"), query)
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlsplit(response["Location"]).query)

    def test_connecting_asks_strava_to_allow_uploads_and_nothing_to_read_activities(self):
        query = self.start()
        self.assertEqual(query["scope"], ["read,activity:write"])
        self.assertEqual(query["client_id"], ["65938"])
        self.assertTrue(query["redirect_uri"][0].endswith(reverse("virtual_ride_strava_callback")))

    @mock.patch("trainer.strava.requests.post")
    def test_coming_back_with_the_upload_permission_connects_strava(self, post):
        later = int((timezone.now() + timedelta(hours=6)).timestamp())
        post.return_value = _answer(
            200,
            {
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": later,
                "athlete": {"id": 42, "firstname": "Anna", "lastname": "R"},
            },
        )
        with translation_override("kk"):
            trainer = reverse("virtual_ride")
        state = self.start(next=trainer)["state"][0]
        back = self.client.get(
            reverse("virtual_ride_strava_callback"), {"state": state, "code": "c", "scope": "read,activity:write"}
        )
        self.assertRedirects(back, trainer, fetch_redirect_response=False)
        connection = StravaConnection.objects.get(user=self.user)
        self.assertEqual((connection.athlete_id, connection.athlete_name), (42, "Anna R"))
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "authorization_code")

    @mock.patch("trainer.strava.requests.post")
    def test_no_connection_from_a_stranger_s_answer_or_without_the_upload_permission(self, post):
        self.start()
        self.client.get(
            reverse("virtual_ride_strava_callback"), {"state": "forged", "code": "c", "scope": "read,activity:write"}
        )
        state = self.start()["state"][0]
        self.client.get(reverse("virtual_ride_strava_callback"), {"state": state, "code": "c", "scope": "read"})
        post.assert_not_called()
        self.assertFalse(StravaConnection.objects.exists())

    def test_a_return_address_off_the_site_is_ignored(self):
        self.start(next="https://evil.example/")
        self.assertTrue(self.client.session["virtual_ride_strava"]["next"].startswith(reverse("account_profile")))

    def test_an_unconfirmed_account_cannot_connect(self):
        self.client.force_login(_user("guest", role=User.Role.GUEST))
        self.assertEqual(self.client.get(reverse("virtual_ride_strava_connect")).status_code, 404)


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class StravaProfileTests(TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client.force_login(self.user)

    def test_the_profile_offers_strava_with_its_own_button(self):
        page = self.client.get(reverse("account_profile"))
        self.assertContains(page, 'class="social-btn social-btn--strava"')
        self.assertContains(page, f'href="{reverse("virtual_ride_strava_connect")}"')

    def test_a_connected_member_can_turn_it_off_and_open_their_rides_on_strava(self):
        _connect(self.user)
        ride = VirtualRide.objects.create(user=self.user, route="center", duration_s=60, distance_m=400)
        StravaUpload.objects.create(ride=ride, status=StravaUpload.Status.DONE, activity_id="77")
        page = self.client.get(reverse("account_profile"))
        self.assertContains(page, f'action="{reverse("virtual_ride_strava_disconnect")}"')
        self.assertContains(
            page,
            '<a href="https://www.strava.com/activities/77" class="fw-semibold" target="_blank" rel="noopener">'
            "View on Strava</a>",
            html=True,
        )

    @mock.patch("trainer.strava.requests.post")
    def test_disconnecting_from_the_profile_forgets_strava(self, post):
        _connect(self.user)
        self.client.post(reverse("virtual_ride_strava_disconnect"))
        self.assertFalse(StravaConnection.objects.exists())


class PrivacyTests(TestCase):
    def test_the_privacy_policy_says_what_the_virtual_ride_keeps_and_sends_to_strava(self):
        body = Client().get(in_language(reverse("privacy_policy"), "en")).content.decode()
        self.assertIn("upload each ride you finish as a virtual ride", body)
        self.assertIn("we still do not read your Strava activities", body)
