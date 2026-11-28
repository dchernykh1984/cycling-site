"""Heart rate variability on the virtual ride: the RR intervals a strap sends, kept with the ride and sent as FIT."""

import struct
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings

from tests.test_virtual_ride_api import MemberClientMixin, _ride, _user
from tests.test_virtual_ride_intervals import _calls, _connected
from tests.test_virtual_ride_strava import STRAVA_ON, _answer, _connect, _track
from trainer import fit, strava
from trainer.models import VirtualRide

RR = [812, 805, 799, 790, 801, 820, 815]


def _messages(data: bytes) -> list[tuple[int, dict[int, list[int]]]]:
    """A FIT file read back as (global message number, {field: [values]}), its header's and its own CRC checked."""
    size, _protocol, _profile, length, magic, header_crc = struct.unpack("<BBHI4sH", data[:14])
    assert (size, magic, header_crc) == (14, b".FIT", fit._crc(data[:12]))
    assert struct.unpack("<H", data[-2:])[0] == fit._crc(data[:-2]) and length == len(data) - 16
    types = {0x00: "B", 0x02: "B", 0x84: "H", 0x85: "i", 0x86: "I", 0x8C: "I"}
    at, local, out = 14, {}, []
    while at < len(data) - 2:
        head = data[at]
        at += 1
        if head & 0x40:  # a definition: little-endian, its message number and fields
            _reserved, arch, number, count = struct.unpack("<BBHB", data[at : at + 5])
            assert arch == 0
            fields = [struct.unpack("<BBB", data[at + 5 + 3 * i : at + 8 + 3 * i]) for i in range(count)]
            local[head & 0xF] = (number, fields)
            at += 5 + 3 * count
            continue
        number, fields = local[head & 0xF]
        values = {}
        for num, width, kind in fields:
            item = struct.calcsize("<" + types[kind])
            values[num] = list(struct.unpack(f"<{width // item}{types[kind]}", data[at : at + width]))
            at += width
        out.append((number, values))
    return out


class FitFileTests(TestCase):
    def test_a_ride_s_fit_file_carries_its_points_and_its_rr_intervals_five_a_message(self):
        ride = SimpleNamespace(
            pk=7, finished_at=datetime(2026, 11, 28, 13, 0, tzinfo=UTC), duration_s=3.0, distance_m=16.0,
            avg_power_w=201, elevation_gain_m=2,
        )  # fmt: skip
        messages = _messages(fit.activity(ride, _track(), RR))
        kinds = [number for number, _ in messages]
        self.assertEqual(kinds[0], fit.FILE_ID)
        self.assertEqual(kinds.count(fit.RECORD), 3)
        self.assertEqual(kinds[-3:], [fit.LAP, fit.SESSION, fit.ACTIVITY])
        hrv = [values[0] for number, values in messages if number == fit.HRV]
        # seconds at scale 1000, the last message's empty places "none"
        self.assertEqual(hrv, [RR[:5], [*RR[5:], 0xFFFF, 0xFFFF, 0xFFFF]])
        first = next(values for number, values in messages if number == fit.RECORD)
        self.assertEqual((first[3], first[4], first[7]), ([140], [88], [200]))  # pulse, cadence, power
        self.assertEqual(first[0], [round(43.2402 * 2**31 / 180)])  # the latitude in semicircles
        session = next(values for number, values in messages if number == fit.SESSION)
        self.assertEqual((session[5], session[6]), ([2], [58]))  # cycling, a virtual activity


@override_settings(SOCIALACCOUNT_PROVIDERS=STRAVA_ON)
class RrSavedAndSentTests(MemberClientMixin, TestCase):
    def setUp(self):
        self.user = _user("anna")
        self.client_m = self.member(self.user)

    def save(self, **overrides):
        return self.post(self.client_m, "/rides", _ride(track=_track(), **overrides))

    def test_the_rr_intervals_are_kept_with_the_track(self):
        self.assertEqual(self.save(rr=RR).status_code, 201)
        self.assertEqual(VirtualRide.objects.get().track.rr, RR)

    def test_an_rr_interval_no_heart_beats_in_is_refused(self):
        for wrong in ([100], [3000]):
            with self.subTest(rr=wrong):
                self.assertEqual(self.save(rr=wrong).status_code, 422)
        self.assertFalse(VirtualRide.objects.exists())

    @mock.patch("trainer.strava.requests.request")
    def test_a_ride_with_rr_intervals_goes_to_strava_as_a_fit_file(self, call):
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "991", "status": "Your activity is still being processed."})
        self.save(rr=RR)
        sent = call.call_args.kwargs
        name, content, _type = sent["files"]["file"]
        self.assertEqual((sent["data"]["data_type"], sent["data"]["sport_type"]), ("fit", "VirtualRide"))
        self.assertTrue(name.endswith(".fit"))
        self.assertIn(fit.HRV, [number for number, _ in _messages(content)])

    @mock.patch("trainer.strava.requests.request")
    def test_a_ride_without_them_goes_as_the_tcx_it_always_did(self, call):
        _connect(self.user)
        call.return_value = _answer(201, {"id_str": "991"})
        self.save()
        self.assertEqual(call.call_args.kwargs["data"]["data_type"], "tcx.gz")

    @mock.patch("trainer.intervals.requests.request")
    def test_a_ride_with_rr_intervals_goes_to_intervals_icu_as_a_fit_file(self, call):
        _connected(self.user)
        call.side_effect = [_answer(201, {"id": "i9876", "activities": [{"id": "i9876"}]}), _answer(200)]
        self.save(rr=RR)
        name, content, _type = _calls(call, "POST")[0].kwargs["files"]["file"]
        self.assertTrue(name.endswith(".fit"))
        self.assertEqual(content, strava.ride_file(VirtualRide.objects.get(), VirtualRide.objects.get().track)[1])
