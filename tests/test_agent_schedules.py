"""When the three agents are told to run, and why the hour matters.

The model bills double inside two windows (01:00-04:00 and 06:00-10:00 UTC), and GitHub starts a
cron only when it has capacity -- our own runs have drifted more than five hours on a bad day. So
the slot is not decoration: an hour picked without that margin quietly doubles the bill, which is
exactly what happened at the end of August 2026.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS = {
    "events": ".github/workflows/agent.yml",
    "instagram": ".github/workflows/instagram-agent.yml",
    "telegram": ".github/workflows/telegram-agent.yml",
}

#: The model's peak windows, in UTC hours, as [start, end).
PEAK_WINDOWS = ((1, 4), (6, 10))

#: How much later than its nominal minute a run may start and still be off-peak. GitHub's drift on
#: this repository has reached five hours; ten leaves room for a worse day.
DRIFT_ALLOWANCE_HOURS = 10


def _cron(name):
    text = Path(WORKFLOWS[name]).read_text(encoding="utf-8")
    found = re.findall(r'^\s*- cron: "([^"]+)"', text, flags=re.M)
    assert len(found) == 1, f"{name}: expected exactly one schedule, found {found}"
    minute, hour, dom, month, dow = found[0].split()
    return {"minute": int(minute), "hour": int(hour), "dom": dom, "month": month, "dow": dow}


def _hours_until_peak(hour):
    """Hours from ``hour`` to the start of the next peak window."""
    return min((start - hour) % 24 for start, _end in PEAK_WINDOWS)


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_no_agent_starts_inside_a_peak_window(name):
    hour = _cron(name)["hour"]
    for start, end in PEAK_WINDOWS:
        assert not (start <= hour < end), f"{name} starts at {hour}:00 UTC, inside peak {start}-{end}"


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_every_agent_keeps_a_margin_for_github_cron_drift(name):
    hour = _cron(name)["hour"]
    margin = _hours_until_peak(hour)
    assert margin >= DRIFT_ALLOWANCE_HOURS, (
        f"{name} starts {margin}h before a peak window; a late start would be billed double"
    )


def test_the_web_agent_reads_the_sources_twice_a_week():
    """The expensive agent: 27 sources and 20-40 minutes against 1-4 for the other two.

    Websites announce weeks ahead, so Monday and Friday cost nothing in lead time.
    """
    cron = _cron("events")
    assert cron["dow"] == "1,5", f"expected Monday and Friday, got {cron['dow']!r}"
    assert cron["dom"] == "*" and cron["month"] == "*"


@pytest.mark.parametrize("name", ["instagram", "telegram"])
def test_the_short_notice_agents_still_run_every_night(name):
    """Club posts and chat announcements are days old at most; a weekly read would miss them."""
    cron = _cron(name)
    assert (cron["dow"], cron["dom"], cron["month"]) == ("*", "*", "*")


def test_the_agents_run_in_the_order_that_lets_each_see_the_last():
    """The Telegram agent dedups against what the other two just proposed, so it goes last."""
    hours = {name: _cron(name)["hour"] for name in WORKFLOWS}
    assert hours["events"] < hours["instagram"] < hours["telegram"]
    assert hours["instagram"] - hours["events"] >= 1, "the web agent runs up to 40 minutes"


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_no_agent_starts_on_the_round_hour(name):
    """Cron congestion peaks on the hour, and a queued run drifts further."""
    assert _cron(name)["minute"] != 0
