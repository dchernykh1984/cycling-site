"""A planned workout in Zwift's ZWO form, read into the steps the trainer page rides (issue #471, phase 2).

intervals.icu hands a planned workout out as a ZWO file (``download.zwo``). Zwift publishes no
specification of the form; what is read here follows the workouts Zwift ships, as catalogued in
https://github.com/h4l/zwift-workout-file-reference:

- power is a fraction of FTP (0.75 is 75 %), unless the file names its own FTP in ``ftpOverride``;
- ``Warmup``, ``Cooldown`` and ``Ramp`` move from ``PowerLow`` at their start to ``PowerHigh`` at their
  end, as the reference's own examples say (a cooldown from 1 to 0.25 is "100W - 25W");
- ``IntervalsT`` repeats ``OnDuration`` at ``OnPower`` and ``OffDuration`` at ``OffPower``;
- ``FreeRide`` and ``MaxEffort`` set no power: the rider rides them by feel;
- a ``textevent`` says its ``message`` ``timeoffset`` seconds into the element that holds it.

Each step comes out with its duration, the power at its start and at its end in watts (equal for a
steady step, none for a free one) and the cadence it asks for, if any; the cues come out apart, each at
its second from the workout's start. The file is somebody else's: it is parsed without DTDs or entities,
and every number in it is bounded.
"""

import math
import re

from defusedxml import DefusedXmlException, ElementTree

MAX_BYTES = 512 * 1024
# a ride's track keeps six hours, and a workout longer than that is cut where the ride would end
MAX_SECONDS = 6 * 3600
MAX_STEPS = 500
MAX_CUES = 200
MAX_REPEATS = 100
MAX_WATTS = 3000
MAX_CUE_CHARS = 200
_CADENCE = (20, 200)
_CUES = {"textevent", "TextEvent"}


class ZwoError(Exception):
    """The file is not a workout this page can ride."""


class NoFtpError(ZwoError):
    """The workout sets power as a share of FTP, and no FTP was given for it."""


def _number(element, name: str) -> float | None:
    value = element.get(name)
    try:
        number = float(value) if value is not None else None
    except ValueError:
        return None
    return number if number is not None and math.isfinite(number) else None


def _power(element, name: str, low: str, high: str) -> float | None:
    """``name``, or else the middle of the range ``low`` to ``high`` (or its one end the file gives)."""
    value = _number(element, name)
    if value is not None:
        return value
    ends = [v for v in (_number(element, low), _number(element, high)) if v is not None]
    return sum(ends) / len(ends) if ends else None


def _cadence(element, name: str = "Cadence") -> int | None:
    rpm = _power(element, name, "CadenceLow", "CadenceHigh") if name == "Cadence" else _number(element, name)
    return round(rpm) if rpm is not None and _CADENCE[0] <= rpm <= _CADENCE[1] else None


class _Reader:
    def __init__(self, ftp: float | None):
        self.ftp = ftp
        self.steps: list[dict] = []
        self.cues: list[dict] = []
        self.at = 0  # seconds from the workout's start to the next step

    def watts(self, fraction: float | None) -> int | None:
        if fraction is None:
            return None
        if not self.ftp:
            raise NoFtpError("The workout sets power as a share of FTP, and no FTP was given for it")
        return round(min(max(fraction * self.ftp, 0), MAX_WATTS))

    def full(self) -> bool:
        return self.at >= MAX_SECONDS or len(self.steps) >= MAX_STEPS

    def step(self, seconds: float | None, start: int | None, end: int | None, cadence: int | None) -> None:
        if seconds is None or seconds < 1 or self.full():
            return
        seconds = min(round(seconds), MAX_SECONDS - self.at)
        self.steps.append({"duration_s": seconds, "power_w": start, "power_end_w": end, "cadence_rpm": cadence})
        self.at += seconds

    def cue(self, element, start: int) -> None:
        text = re.sub(r"\s+", " ", element.get("message") or element.get("mssage") or "").strip()[:MAX_CUE_CHARS]
        offset = _number(element, "timeoffset")
        offset = offset if offset is not None else _number(element, "TimeOffset")
        if text and len(self.cues) < MAX_CUES:
            self.cues.append({"at_s": start + max(round(offset or 0), 0), "text": text})

    def steady(self, element) -> None:
        watts = self.watts(_power(element, "Power", "PowerLow", "PowerHigh"))
        self.step(_number(element, "Duration"), watts, watts, _cadence(element))

    def ramp(self, element) -> None:
        low, high = _number(element, "PowerLow"), _number(element, "PowerHigh")
        if low is None or high is None:  # one power given: a steady step
            low = high = next((v for v in (low, high, _number(element, "Power")) if v is not None), None)
        self.step(_number(element, "Duration"), self.watts(low), self.watts(high), _cadence(element))

    def intervals(self, element) -> None:
        on = self.watts(_power(element, "OnPower", "PowerOnLow", "PowerOnHigh"))
        off = self.watts(_power(element, "OffPower", "PowerOffLow", "PowerOffHigh"))
        repeats = min(max(round(_number(element, "Repeat") or 1), 1), MAX_REPEATS)
        for _ in range(repeats):
            self.step(_number(element, "OnDuration"), on, on, _cadence(element))
            self.step(_number(element, "OffDuration"), off, off, _cadence(element, "CadenceResting"))

    def free(self, element) -> None:
        # a free ride, an all-out effort, or a step this page does not know: its time is kept, by feel
        self.step(_number(element, "Duration"), None, None, _cadence(element))

    def element(self, element) -> None:
        start = self.at
        if element.tag in _CUES:
            self.cue(element, 0)  # a cue of the workout's own: from its start
            return
        _KINDS.get(element.tag, _Reader.free)(self, element)
        for child in element:
            if child.tag in _CUES:
                self.cue(child, start)


_KINDS = {
    "SteadyState": _Reader.steady,
    "SolidState": _Reader.steady,
    "Warmup": _Reader.ramp,
    "Cooldown": _Reader.ramp,
    "Ramp": _Reader.ramp,
    "IntervalsT": _Reader.intervals,
}


def _ftp_override(root) -> float | None:
    found = root.find("ftpOverride")
    try:
        value = float((found.text or "").strip()) if found is not None else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) and value > 0 else None


def parse(data: bytes, ftp: float | None) -> dict:
    """The steps and cues of a ZWO file, in watts from ``ftp`` (or the file's own ``ftpOverride``)."""
    if len(data) > MAX_BYTES:
        raise ZwoError("The workout file is too large")
    try:
        root = ElementTree.fromstring(data, forbid_dtd=True)
    except (ElementTree.ParseError, DefusedXmlException):
        raise ZwoError("The workout file could not be read") from None
    workout = root if root.tag == "workout" else root.find("workout")
    if workout is None:
        raise ZwoError("The file holds no workout")
    reader = _Reader(_ftp_override(root) or ftp)
    for element in workout:
        if reader.full():
            break
        reader.element(element)
    if not reader.steps:
        raise ZwoError("The workout has no steps to ride")
    cues = [cue for cue in reader.cues if cue["at_s"] < reader.at]  # none past the workout's end
    return {"steps": reader.steps, "cues": sorted(cues, key=lambda cue: cue["at_s"])}
