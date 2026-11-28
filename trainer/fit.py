"""A ride as a FIT activity file: what Strava and intervals.icu take when it carries the rider's RR intervals.

A TCX has no place for heart rate variability; FIT has, its ``hrv`` message -- the RR intervals one after another, in
seconds. Written with the FIT protocol's own layout (a 14-byte header, a definition message before each kind of data
message, a CRC over everything), the messages a device writes for a ride: the file's id, a timer start, a record a
second, the RR intervals, a timer stop, the lap, the session and the activity. Only what this ride has is written.
"""

import struct
from datetime import UTC, datetime, timedelta

from .models import VirtualRide

# seconds from the Unix epoch to the FIT one, 1989-12-31 00:00 UTC
_FIT_EPOCH = 631065600
_PROFILE_VERSION = 2132
_PROTOCOL_VERSION = 0x20
# the FIT base types: (code, struct format, the value that stands for none)
ENUM, UINT8, UINT16, SINT32, UINT32, UINT32Z = (
    (0x00, "B", 0xFF),
    (0x02, "B", 0xFF),
    (0x84, "H", 0xFFFF),
    (0x85, "i", 0x7FFFFFFF),
    (0x86, "I", 0xFFFFFFFF),
    (0x8C, "I", 0),
)
# message numbers and the values the profile gives them
FILE_ID, LAP, SESSION, RECORD, EVENT, ACTIVITY, HRV = 0, 19, 18, 20, 21, 34, 78
_ACTIVITY_FILE, _DEVELOPMENT, _CYCLING, _VIRTUAL_ACTIVITY = 4, 255, 2, 58
_TIMER, _START, _STOP, _STOP_ALL, _LAP_EVENT, _SESSION_EVENT, _ACTIVITY_EVENT = 0, 0, 1, 4, 9, 8, 26
# RR intervals an hrv message carries, as a device writes them
HRV_PER_MESSAGE = 5
_SEMICIRCLES = 2**31 / 180


def _crc(data: bytes, crc: int = 0) -> int:
    """The FIT protocol's CRC-16, four bits at a time."""
    table = (
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
    )  # fmt: skip
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            low = table[crc & 0xF]
            crc = ((crc >> 4) & 0x0FFF) ^ low ^ table[nibble]
    return crc


class _Writer:
    def __init__(self) -> None:
        self.body = bytearray()
        self.defined: dict[int, tuple] = {}

    def message(self, number: int, fields: list[tuple[int, tuple, object]]) -> None:
        """One data message, ``fields`` as (field number, base type, value or list of values); a field without a
        value is left out. Local message type 0 is defined again whenever the shape changes."""
        fields = [(num, kind, value) for num, kind, value in fields if value is not None]
        shape = tuple((num, kind, len(value) if isinstance(value, list) else 1) for num, kind, value in fields)
        if self.defined.get(0) != (number, shape):
            self.defined[0] = (number, shape)
            self.body += struct.pack("<BBBHB", 0x40, 0, 0, number, len(shape))
            for num, kind, count in shape:
                self.body += struct.pack("<BBB", num, struct.calcsize("<" + kind[1]) * count, kind[0])
        self.body.append(0)
        for _num, kind, value in fields:
            for item in value if isinstance(value, list) else [value]:
                self.body += struct.pack("<" + kind[1], item)

    def file(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, _PROTOCOL_VERSION, _PROFILE_VERSION, len(self.body), b".FIT")
        header += struct.pack("<H", _crc(header))
        data = header + bytes(self.body)
        return data + struct.pack("<H", _crc(data))


def _stamp(moment: datetime) -> int:
    return int(moment.astimezone(UTC).timestamp()) - _FIT_EPOCH


def _bounded(value: float, kind: tuple) -> int | None:
    """A value as its field holds it, or none when it does not fit."""
    number = round(value)
    limit = {"B": 0xFE, "H": 0xFFFE, "I": 0xFFFFFFFE}.get(kind[1])
    return number if limit is None or 0 <= number <= limit else None


def activity(ride: VirtualRide, points: list, rr_ms: list[int]) -> bytes:
    """The ride as a FIT activity: its track, a point a second, and the rider's RR intervals in milliseconds."""
    start = ride.finished_at - timedelta(seconds=ride.duration_s)
    end = _stamp(ride.finished_at)
    out = _Writer()
    out.message(
        FILE_ID,
        [(0, ENUM, _ACTIVITY_FILE), (1, UINT16, _DEVELOPMENT), (2, UINT16, 1), (3, UINT32Z, ride.pk or 1),
         (4, UINT32, _stamp(start))],
    )  # fmt: skip
    out.message(EVENT, [(253, UINT32, _stamp(start)), (0, ENUM, _TIMER), (1, ENUM, _START)])
    for t, lat, lon, ele, distance, speed, power, cadence, pulse in points:
        out.message(
            RECORD,
            [
                (253, UINT32, _stamp(start + timedelta(seconds=t))),
                (0, SINT32, round(lat * _SEMICIRCLES)),
                (1, SINT32, round(lon * _SEMICIRCLES)),
                (2, UINT16, _bounded((ele + 500) * 5, UINT16)),  # scale 5, offset 500 m
                (3, UINT8, _bounded(pulse, UINT8) if pulse else None),
                (4, UINT8, _bounded(cadence, UINT8) if cadence else None),
                (5, UINT32, _bounded(distance * 100, UINT32)),
                (6, UINT16, _bounded(speed * 1000, UINT16)),
                (7, UINT16, _bounded(power, UINT16)),
            ],
        )
    # the RR intervals in seconds, scale 1000, five a message; the last one's empty places hold "none"
    for i in range(0, len(rr_ms), HRV_PER_MESSAGE):
        chunk = [_bounded(ms, UINT16) or UINT16[2] for ms in rr_ms[i : i + HRV_PER_MESSAGE]]
        out.message(HRV, [(0, UINT16, chunk + [UINT16[2]] * (HRV_PER_MESSAGE - len(chunk)))])
    out.message(EVENT, [(253, UINT32, end), (0, ENUM, _TIMER), (1, ENUM, _STOP_ALL)])
    elapsed = round(ride.duration_s * 1000)
    distance = _bounded(ride.distance_m * 100, UINT32)
    pulses = [p[8] for p in points if p[8]]
    summary = [
        (253, UINT32, end),
        (2, UINT32, _stamp(start)),
        (7, UINT32, elapsed),
        (8, UINT32, elapsed),
        (9, UINT32, distance),
    ]
    out.message(
        LAP, [*summary, (0, ENUM, _LAP_EVENT), (1, ENUM, _STOP), (25, ENUM, _CYCLING), (39, ENUM, _VIRTUAL_ACTIVITY)]
    )
    out.message(
        SESSION,
        [
            *summary,
            (0, ENUM, _SESSION_EVENT),
            (1, ENUM, _STOP),
            (5, ENUM, _CYCLING),
            (6, ENUM, _VIRTUAL_ACTIVITY),
            (16, UINT8, _bounded(sum(pulses) / len(pulses), UINT8) if pulses else None),
            (17, UINT8, _bounded(max(pulses), UINT8) if pulses else None),
            (20, UINT16, _bounded(ride.avg_power_w, UINT16) if ride.avg_power_w else None),
            (22, UINT16, _bounded(ride.elevation_gain_m, UINT16)),
            (25, UINT16, 0),
            (26, UINT16, 1),
        ],
    )
    out.message(
        ACTIVITY,
        [(253, UINT32, end), (0, UINT32, elapsed), (1, UINT16, 1), (2, ENUM, 0), (3, ENUM, _ACTIVITY_EVENT),
         (4, ENUM, _STOP)],
    )  # fmt: skip
    return out.file()
