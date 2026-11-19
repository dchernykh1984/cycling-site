"""Workouts planned in intervals.icu, ridden on the trainer page (issue #471, phase 2).

The workouts are read from the member's intervals.icu with their own key, and the power is turned into
watts with the FTP intervals.icu gives; nothing of them is kept. Every call to intervals.icu is a
patched ``requests.request``.
"""

import sys
from datetime import date
from unittest import mock

import requests
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.views.debug import ExceptionReporter

from tests.test_virtual_ride_api import _user
from tests.test_virtual_ride_intervals import COUNTING_CACHE, KEY, OTHER_SITE_KEY, _connected, _page
from trainer import intervals, zwo
from trainer.models import IntervalsConnection


def _zwo(*elements: str, head: str = "") -> bytes:
    return f"<workout_file><name>W</name>{head}<workout>{''.join(elements)}</workout></workout_file>".encode()


def _json(body, status=200):
    response = mock.Mock(status_code=status, text="")
    response.json.return_value = body
    return response


def _file(data: bytes, status=200):
    response = mock.Mock(status_code=status, content=data, text=data.decode())
    response.json.side_effect = requests.JSONDecodeError("Expecting value", "<", 0)
    return response


def _steps(*rows):
    return [{"duration_s": d, "power_w": a, "power_end_w": b, "cadence_rpm": c} for d, a, b, c in rows]


class ZwoTests(SimpleTestCase):
    def test_steady_steps_and_ramps_come_out_in_watts_from_the_ftp(self):
        parsed = zwo.parse(
            _zwo(
                '<Warmup Duration="600" PowerLow="0.25" PowerHigh="0.75"/>',
                '<SteadyState Duration="300" Power="0.9" Cadence="95"/>',
                '<Ramp Duration="120" PowerLow="0.5" PowerHigh="1.0"/>',
                '<Cooldown Duration="300" PowerLow="0.7" PowerHigh="0.3"/>',
            ),
            200,
        )
        # a warm-up, a ramp and a cool-down move from PowerLow at their start to PowerHigh at their end
        self.assertEqual(
            parsed["steps"],
            _steps((600, 50, 150, None), (300, 180, 180, 95), (120, 100, 200, None), (300, 140, 60, None)),
        )
        self.assertEqual(parsed["cues"], [])

    def test_repeated_intervals_unfold_with_their_cadences(self):
        parsed = zwo.parse(
            _zwo(
                '<IntervalsT Repeat="3" OnDuration="60" OffDuration="30" OnPower="1.2" OffPower="0.5"'
                ' Cadence="100" CadenceResting="85"/>'
            ),
            200,
        )
        self.assertEqual(parsed["steps"], _steps(*[(60, 240, 240, 100), (30, 100, 100, 85)] * 3))

    def test_a_free_ride_and_an_all_out_effort_set_no_power(self):
        parsed = zwo.parse(
            _zwo(
                '<FreeRide Duration="600" Cadence="90"/>',
                '<MaxEffort Duration="20"/>',
                '<Unheard Duration="30"/>',  # a step this page does not know keeps its time, by feel
                "<RestDay/>",
            ),
            None,  # no power is asked, so none is needed
        )
        self.assertEqual(parsed["steps"], _steps((600, None, None, 90), (20, None, None, None), (30, None, None, None)))

    def test_power_ranges_and_cadence_ranges_are_ridden_at_their_middle(self):
        parsed = zwo.parse(
            _zwo(
                '<SteadyState Duration="60" PowerLow="0.88" PowerHigh="0.94" CadenceLow="85" CadenceHigh="95"/>',
                '<IntervalsT Repeat="1" OnDuration="30" OffDuration="30" PowerOnLow="1.1" PowerOnHigh="1.3"'
                ' PowerOffLow="0.4" PowerOffHigh="0.6"/>',
                '<Warmup Duration="60" Power="0.6"/>',  # a warm-up with one power is a steady step
            ),
            200,
        )
        self.assertEqual(
            parsed["steps"],
            _steps((60, 182, 182, 90), (30, 240, 240, None), (30, 100, 100, None), (60, 120, 120, None)),
        )

    def test_cues_fall_at_their_second_from_the_workout_s_start(self):
        parsed = zwo.parse(
            _zwo(
                '<textevent timeoffset="5" message="Welcome"/>',
                '<SteadyState Duration="300" Power="0.5"><textevent timeoffset="10" message=" Easy \n now "/>'
                "</SteadyState>",
                '<IntervalsT Repeat="2" OnDuration="60" OffDuration="60" OnPower="1" OffPower="0.5">'
                '<TextEvent TimeOffset="150" message="Second one"/></IntervalsT>',
                '<SteadyState Duration="60" Power="0.5"><textevent timeoffset="900" message="Past the end"/>'
                '<textevent timeoffset="0" message=""/></SteadyState>',
            ),
            200,
        )
        # a cue inside a step counts from the step's start, inside repeats from the first one's; none past the end
        self.assertEqual(
            parsed["cues"],
            [{"at_s": 5, "text": "Welcome"}, {"at_s": 10, "text": "Easy now"}, {"at_s": 450, "text": "Second one"}],
        )

    def test_a_file_with_its_own_ftp_is_ridden_from_it(self):
        parsed = zwo.parse(_zwo('<SteadyState Duration="60" Power="0.5"/>', head="<ftpOverride>300</ftpOverride>"), 200)
        self.assertEqual(parsed["steps"], _steps((60, 150, 150, None)))

    def test_power_without_an_ftp_is_refused(self):
        with self.assertRaises(zwo.NoFtpError):
            zwo.parse(_zwo('<SteadyState Duration="60" Power="0.5"/>'), None)

    def test_a_file_that_is_no_workout_is_refused(self):
        laughs = (
            b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
            b"<workout_file><workout><textevent message='&lol2;'/></workout></workout_file>"
        )
        for data in (
            b"not a file at all",
            laughs,  # no DTD, so no entity can grow
            b"<workout_file><name>W</name></workout_file>",
            _zwo(),
            _zwo('<SteadyState Duration="0" Power="0.5"/>'),
            _zwo('<SteadyState Duration="60" Power="0.5"/>', head=" " * zwo.MAX_BYTES),
        ):
            with self.assertRaises(zwo.ZwoError):
                zwo.parse(data, 200)

    def test_every_number_in_the_file_is_bounded(self):
        parsed = zwo.parse(
            _zwo(
                '<SteadyState Duration="60" Power="50" Cadence="500"/>',  # 5000 % of FTP, 500 rpm
                '<SteadyState Duration="60" Power="-1"/>',
                '<SteadyState Duration="0.4" Power="0.5"/>',  # shorter than a second: nothing to ride
                '<SteadyState Duration="60" Power="nan"/>',  # no number: ridden by feel
                '<IntervalsT Repeat="1000" OnDuration="1" OffDuration="1" OnPower="1" OffPower="0.5"/>',
            ),
            200,
        )
        steps = parsed["steps"]
        self.assertEqual(
            steps[:3], _steps((60, zwo.MAX_WATTS, zwo.MAX_WATTS, None), (60, 0, 0, None), (60, None, None, None))
        )
        self.assertEqual(len(steps), 3 + 2 * zwo.MAX_REPEATS)

    def test_a_workout_longer_than_a_ride_is_cut_where_the_ride_ends(self):
        parsed = zwo.parse(
            _zwo(
                '<SteadyState Duration="3600" Power="0.5"/>',
                '<SteadyState Duration="30000" Power="0.6"/>',
                '<FreeRide Duration="60"/>',
            ),
            200,
        )
        self.assertEqual([s["duration_s"] for s in parsed["steps"]], [3600, zwo.MAX_SECONDS - 3600])
        many = zwo.parse(_zwo(*['<SteadyState Duration="1" Power="0.5"/>'] * (zwo.MAX_STEPS + 5)), 200)
        self.assertEqual(len(many["steps"]), zwo.MAX_STEPS)

    def test_cues_are_bounded_in_number_and_length(self):
        long = "x" * (zwo.MAX_CUE_CHARS + 50)
        cues = "".join(f'<textevent timeoffset="{i}" message="{long}"/>' for i in range(zwo.MAX_CUES + 10))
        parsed = zwo.parse(_zwo(f'<SteadyState Duration="3600" Power="0.5">{cues}</SteadyState>'), 200)
        self.assertEqual(len(parsed["cues"]), zwo.MAX_CUES)
        self.assertEqual({len(cue["text"]) for cue in parsed["cues"]}, {zwo.MAX_CUE_CHARS})


_EVENTS = [
    {"id": 7, "type": "Run", "category": "WORKOUT", "name": "Tempo run", "start_date_local": "2026-11-20T00:00:00"},
    {"id": 9, "type": "Ride", "category": "WORKOUT", "name": "Sweet spot", "moving_time": 3600,
     "start_date_local": "2026-11-21T00:00:00"},
    {"id": 8, "type": "VirtualRide", "category": "WORKOUT", "name": "Openers",
     "start_date_local": "2026-11-20T18:00:00"},
    {"type": "Ride", "name": "no id"},
    {"id": "x", "type": "Ride", "name": "not a number"},
    "not an event",
]  # fmt: skip
_EVENT = {"id": 9, "type": "Ride", "category": "WORKOUT", "name": "Sweet spot", "start_date_local": "2026-11-21",
          "moving_time": 900, "icu_ftp": 250}  # fmt: skip
_SWEET_SPOT = _zwo(
    '<Warmup Duration="300" PowerLow="0.4" PowerHigh="0.8"/>',
    '<SteadyState Duration="600" Power="0.9" Cadence="90"><textevent timeoffset="0" message="Hold it"/></SteadyState>',
)


class PlannedWorkoutsTests(TestCase):
    def setUp(self):
        self.user = _user("anna")

    @mock.patch("trainer.intervals.requests.request")
    def test_the_week_s_cycling_workouts_are_listed_by_day(self, call):
        _connected(self.user)
        call.return_value = _json(_EVENTS)
        listed = intervals.planned_workouts(self.user, date(2026, 11, 20))
        self.assertEqual(call.call_args.args, ("GET", f"{intervals.API}/athlete/i42/events"))
        self.assertEqual(
            call.call_args.kwargs["params"], {"oldest": "2026-11-20", "newest": "2026-11-27", "category": "WORKOUT"}
        )
        self.assertEqual(call.call_args.kwargs["auth"], ("API_KEY", KEY))
        self.assertEqual(
            listed,
            [
                {"id": 8, "date": "2026-11-20", "name": "Openers", "duration_s": None},
                {"id": 9, "date": "2026-11-21", "name": "Sweet spot", "duration_s": 3600},
            ],
        )

    def test_reading_workouts_needs_a_connection_the_site_can_open(self):
        with self.assertRaises(intervals.NotConnectedError):
            intervals.planned_workouts(self.user, date(2026, 11, 20))
        _connected(self.user)
        with (
            override_settings(INTEGRATIONS_ENCRYPTION_KEY=OTHER_SITE_KEY),
            self.assertRaises(intervals.NotConnectedError),
        ):
            intervals.planned_workouts(self.user, date(2026, 11, 20))
        self.assertFalse(IntervalsConnection.objects.exists(), "a key nobody can read is no connection")

    @mock.patch("trainer.intervals.requests.request")
    def test_a_key_intervals_icu_no_longer_takes_drops_the_connection_and_a_403_does_not(self, call):
        _connected(self.user)
        call.return_value = _json({}, status=403)  # the proxy in front of intervals.icu says this too
        with self.assertRaises(intervals.IntervalsError) as caught:
            intervals.planned_workouts(self.user, date(2026, 11, 20))
        self.assertNotIsInstance(caught.exception, intervals.NotConnectedError)
        self.assertTrue(IntervalsConnection.objects.exists())
        call.return_value = _json({}, status=401)
        with self.assertRaises(intervals.NotConnectedError):
            intervals.planned_workouts(self.user, date(2026, 11, 20))
        self.assertFalse(IntervalsConnection.objects.exists())

    @mock.patch("trainer.intervals.requests.request")
    def test_an_answer_that_is_no_list_fails_the_reading(self, call):
        _connected(self.user)
        for answer in (_page(), _json({"events": []}), _json([], status=500), requests.ConnectionError("down")):
            call.reset_mock(side_effect=True, return_value=True)
            if isinstance(answer, Exception):
                call.side_effect = answer
            else:
                call.return_value = answer
            with self.assertRaises(intervals.IntervalsError):
                intervals.planned_workouts(self.user, date(2026, 11, 20))

    @mock.patch("trainer.intervals.requests.request")
    def test_one_workout_comes_in_watts_from_the_ftp_intervals_icu_gives_it(self, call):
        _connected(self.user)
        call.side_effect = [_json(_EVENT), _file(_SWEET_SPOT)]
        workout = intervals.planned_workout(self.user, 9)
        event, download = call.call_args_list
        self.assertEqual(event.args, ("GET", f"{intervals.API}/athlete/i42/events/9"))
        self.assertEqual(download.args, ("GET", f"{intervals.API}/athlete/i42/events/9/download.zwo"))
        self.assertEqual(download.kwargs["headers"]["Accept"], "*/*")  # a file, which a JSON-only ask may not get
        self.assertEqual(
            workout,
            {
                "id": 9,
                "date": "2026-11-21",
                "name": "Sweet spot",
                "duration_s": 900,
                "ftp_w": 250,
                "steps": _steps((300, 100, 200, None), (600, 225, 225, 90)),
                "cues": [{"at_s": 300, "text": "Hold it"}],
            },
        )

    @mock.patch("trainer.intervals.requests.request")
    def test_without_an_ftp_on_the_workout_the_ride_settings_give_it_indoors_first(self, call):
        _connected(self.user)
        no_ftp = {k: v for k, v in _EVENT.items() if k != "icu_ftp"}
        for ride, expected in (({"ftp": 260, "indoor_ftp": 240}, 240), ({"ftp": 260}, 260)):
            settings = {"sportSettings": [{"types": ["Run"], "ftp": 999}, {"types": ["Ride", "VirtualRide"], **ride}]}
            call.reset_mock(side_effect=True)
            call.side_effect = [_json(no_ftp), _json(settings), _file(_SWEET_SPOT)]
            workout = intervals.planned_workout(self.user, 9)
            self.assertEqual(call.call_args_list[1].args, ("GET", f"{intervals.API}/athlete/i42"))
            self.assertEqual((workout["ftp_w"], workout["steps"][1]["power_w"]), (expected, round(0.9 * expected)))

    @mock.patch("trainer.intervals.requests.request")
    def test_a_workout_by_power_without_any_ftp_says_where_to_set_it(self, call):
        _connected(self.user)
        no_ftp = {k: v for k, v in _EVENT.items() if k != "icu_ftp"}
        call.side_effect = [_json(no_ftp), _json({"sportSettings": [{"types": ["Ride"]}]}), _file(_SWEET_SPOT)]
        with self.assertRaises(intervals.IntervalsError) as caught:
            intervals.planned_workout(self.user, 9)
        self.assertIn("set it there", str(caught.exception))
        # a workout ridden by feel needs no FTP
        call.side_effect = [_json(no_ftp), _json({}), _file(_zwo('<FreeRide Duration="600"/>'))]
        self.assertEqual(intervals.planned_workout(self.user, 9)["ftp_w"], None)

    @mock.patch("trainer.intervals.requests.request")
    def test_a_workout_a_bike_does_not_ride_or_intervals_icu_does_not_have_is_not_found(self, call):
        _connected(self.user)
        for answer in (_json({**_EVENT, "type": "Run"}), _json({**_EVENT, "category": "NOTE"}), _json({}, status=404)):
            call.reset_mock(side_effect=True)
            call.side_effect = [answer]
            with self.assertRaises(intervals.NotFoundError):
                intervals.planned_workout(self.user, 9)
        self.assertEqual(call.call_count, 1, "no file is asked for once the event says no")

    @mock.patch("trainer.intervals.requests.request")
    def test_a_file_that_is_no_workout_fails_the_reading(self, call):
        _connected(self.user)
        call.side_effect = [_json(_EVENT), _file(b"<html>One moment</html>")]
        with self.assertRaises(intervals.IntervalsError) as caught:
            intervals.planned_workout(self.user, 9)
        self.assertNotIsInstance(caught.exception, intervals.NotFoundError)

    @override_settings(CACHES=COUNTING_CACHE)
    @mock.patch("trainer.intervals.requests.request")
    def test_reads_are_held_back_past_the_window_s_allowance(self, call):
        _connected(self.user)
        call.return_value = _json([])
        for _ in range(intervals._READS):
            intervals.planned_workouts(self.user, date(2026, 11, 20))
        call.reset_mock()
        with self.assertRaises(intervals.TooManyTriesError):
            intervals.planned_workouts(self.user, date(2026, 11, 20))
        call.assert_not_called()


def _report_of(act) -> str:
    """The report a server error mails the admins, with every frame's variables."""
    try:
        act()
    except RuntimeError:
        return ExceptionReporter(RequestFactory().get("/"), *sys.exc_info()).get_traceback_html()
    raise AssertionError("nothing went wrong")


class WorkoutErrorReportTests(TestCase):
    """Reading workouts holds the key as connecting does: a server error's report leaves it out."""

    @mock.patch("trainer.intervals.requests.request")
    def test_a_failure_while_reading_workouts_leaves_the_key_out(self, call):
        user = _user("anna")
        _connected(user)
        call.side_effect = RuntimeError("the library broke")  # deep down, where the key travels as auth
        self.assertNotIn(KEY, _report_of(lambda: intervals.planned_workouts(user, date(2026, 11, 20))))
        self.assertNotIn(KEY, _report_of(lambda: intervals.planned_workout(user, 9)))
