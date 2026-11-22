"""The nightly deploy deploys main only when the site runs another commit and main is green (#153)."""

import re
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

from scripts import deploy_if_behind as deploy

MAIN, OLD = "a" * 40, "b" * 40
HOOK = "https://api.render.com/deploy/srv-x?key=secret"
ENV = {"GITHUB_REPOSITORY": "owner/site", "GITHUB_TOKEN": "t", "SITE_BASE_URL": "https://site.test/"}
NIGHT = datetime(2026, 11, 19, 21, 7, tzinfo=UTC)
CI = (".github/workflows/ci.yml", "CI")
DROPBOX = (".github/workflows/dropbox-integration.yml", "Dropbox Integration")


def ran(workflow, conclusion="success"):
    """One run of a workflow on main's push, as GitHub lists it; ``None`` is a run still going."""
    path, name = workflow
    status = "in_progress" if conclusion is None else "completed"
    return {"path": path, "name": name, "status": status, "conclusion": conclusion}


class Answer:
    """What urlopen hands back, as the script reads it."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"commit": "x"}'


class Site:
    """GitHub and the site as the script sees them; a deploy makes the site name main."""

    def __init__(self, live=OLD, runs=None, answers=True, takes=True):
        # what GitHub lists for main's push, ask after ask; the last list stays
        self.runs = runs if runs is not None else [[ran(CI), ran(DROPBOX)]]
        self.live, self.answers, self.takes, self.asked = live, answers, takes, 0
        self.deployed: list[tuple[str, str]] = []
        self.slept: list[float] = []

    def fetch(self, url, token=""):
        if url == "https://site.test/api/v1/version/":
            assert token == "", "the GitHub token goes to GitHub only"
            if not self.answers:
                raise OSError("down")
            return {"commit": self.live}
        assert url.startswith("https://api.github.com/repos/owner/site/") and token == "t", url
        if url.endswith("/commits/main"):
            return {"sha": MAIN}
        path, _, query = url.partition("?")
        assert path.endswith("/repos/owner/site/actions/runs"), url
        # main's own push only: the agents and the deploy run on main's commit too, and check nothing of it
        assert parse_qs(query) == {"head_sha": [MAIN], "event": ["push"], "branch": ["main"], "per_page": ["100"]}
        listed = self.runs[min(self.asked, len(self.runs) - 1)]
        self.asked += 1
        return {"workflow_runs": listed}

    def deploy(self, hook, sha):
        self.deployed.append((hook, sha))
        if self.takes:
            self.live, self.answers = sha, True

    def run(self, env=None, now=NIGHT):
        return deploy.run(
            {**ENV, "RENDER_DEPLOY_HOOK_URL": HOOK, **(env or {})}, now, self.fetch, self.deploy, self.slept.append
        )


def test_nothing_is_deployed_while_the_site_runs_main():
    site = Site(live=MAIN)
    assert site.run() == 0
    assert site.deployed == []


def test_a_site_behind_main_is_deployed_and_waited_for(capsys):
    site = Site()
    assert site.run() == 0
    assert site.deployed == [(HOOK, MAIN)]
    assert "key=secret" not in capsys.readouterr().out


def test_a_site_that_cannot_answer_counts_as_behind():
    site = Site(answers=False)
    assert site.run() == 0
    assert site.deployed == [(HOOK, MAIN)]


def test_a_red_check_on_main_deploys_nothing_and_names_it(capsys):
    for red in ([ran(CI, "failure"), ran(DROPBOX)], [ran(CI), ran(DROPBOX, "failure")], [ran(CI, "cancelled")]):
        site = Site(runs=[red])
        assert site.run() == 1
        assert site.deployed == []
    out = capsys.readouterr().out
    assert "Dropbox Integration (failure)" in out and "CI (cancelled)" in out


def test_a_red_check_deploys_nothing_without_waiting_for_the_others():
    site = Site(runs=[[ran(CI, None), ran(DROPBOX, "failure")]])
    assert site.run() == 1
    assert (site.deployed, site.slept) == ([], [])


def test_a_check_still_running_is_waited_for_then_main_deploys():
    site = Site(runs=[[ran(CI, None), ran(DROPBOX, None)], [ran(CI), ran(DROPBOX, None)], [ran(CI), ran(DROPBOX)]])
    assert site.run() == 0
    assert site.deployed == [(HOOK, MAIN)]
    assert site.slept[:2] == [deploy.POLL_SECONDS] * 2


def test_checks_that_never_finish_or_a_ci_that_never_starts_deploy_nothing(capsys):
    for runs in ([ran(CI, None), ran(DROPBOX)], [ran(DROPBOX)], []):
        site = Site(runs=[runs])
        assert site.run() == 1
        assert site.deployed == []
        assert sum(site.slept) <= deploy.CHECKS_WAIT_SECONDS
    out = capsys.readouterr().out
    assert "did not finish" in out and "CI has not started" in out


def test_a_skipped_check_counts_as_green():
    site = Site(runs=[[ran(CI), ran(DROPBOX, "skipped"), ran((".github/workflows/x.yml", "X"), "neutral")]])
    assert site.run() == 0
    assert site.deployed == [(HOOK, MAIN)]


def test_a_check_started_again_counts_by_its_last_run():
    # GitHub lists the newest run first: a red Dropbox check started again and passed lets main deploy
    again = Site(runs=[[ran(CI), ran(DROPBOX), ran(DROPBOX, "failure")]])
    assert again.run() == 0
    still_red = Site(runs=[[ran(CI), ran(DROPBOX, "failure"), ran(DROPBOX)]])
    assert still_red.run() == 1


def test_without_the_hook_nothing_is_deployed():
    site = Site()
    assert site.run({"RENDER_DEPLOY_HOOK_URL": ""}) == 1
    assert site.deployed == []


def test_a_hook_that_refuses_turns_the_run_red_without_printing_its_address(capsys):
    site = Site()

    def refuse(hook, sha):
        raise urllib.error.HTTPError(hook, 404, "Not Found", None, None)  # type: ignore[arg-type]

    assert deploy.run({**ENV, "RENDER_DEPLOY_HOOK_URL": HOOK}, NIGHT, site.fetch, refuse, lambda s: None) == 1
    out = capsys.readouterr().out
    assert "404" in out
    assert "key=secret" not in out


def test_a_hook_that_cannot_be_reached_turns_the_run_red_in_a_sentence(capsys):
    site = Site()

    def unreachable(hook, sha):
        raise urllib.error.URLError(TimeoutError("timed out"))

    assert deploy.run({**ENV, "RENDER_DEPLOY_HOOK_URL": HOOK}, NIGHT, site.fetch, unreachable, lambda s: None) == 1
    out = capsys.readouterr().out
    assert "could not be reached" in out
    assert "key=secret" not in out


def test_a_deploy_the_site_never_shows_turns_the_run_red():
    site = Site(takes=False)
    assert site.run() == 1
    assert site.deployed == [(HOOK, MAIN)]


def test_a_run_started_outside_its_window_deploys_nothing():
    site = Site()
    late = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)
    assert site.run({"DEPLOY_WINDOW_UTC": "21:00-01:00"}, now=late) == 0
    assert site.deployed == []
    assert site.run({"DEPLOY_WINDOW_UTC": "21:00-01:00"}) == 0
    assert site.deployed == [(HOOK, MAIN)]


def _hours(field: str) -> list[int]:
    """The hours a cron field such as "0,17-23" names."""
    hours: list[int] = []
    for part in field.split(","):
        first, _, last = part.partition("-")
        hours.extend(range(int(first), int(last or first) + 1))
    return hours


def test_a_scheduled_run_starts_inside_the_window_when_github_starts_it_up_to_7_hours_late():
    """GitHub started the one night run 4 to 5 hours late on each of the first three nights
    (2026-11-20 to 22), past the window, and nothing was deployed: a run every hour around the window
    puts one inside it whether GitHub starts them on time or up to 7 hours late."""
    workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy.yml").read_text()
    (cron,) = re.findall(r'cron: "([^"]+)"', workflow)
    minute, hour = cron.split()[:2]
    window = re.search(r"DEPLOY_WINDOW_UTC: .*'(\d\d:\d\d-\d\d:\d\d)'", workflow)
    assert window, "the workflow gives its scheduled runs no window"
    asked = [datetime(2026, 11, 21, h, int(minute), tzinfo=UTC) for h in _hours(hour)]
    for late in range(0, 7 * 60 + 1, 5):
        started = [moment + timedelta(minutes=late) for moment in asked]
        assert any(deploy.in_window(moment, window.group(1)) for moment in started), f"{late} minutes late"


def test_the_window_may_cross_midnight():
    def at(hour, minute=0):
        return datetime(2026, 11, 19, hour, minute, tzinfo=UTC)

    assert deploy.in_window(at(21), "21:00-01:00")
    assert deploy.in_window(at(0, 59), "21:00-01:00")
    assert not deploy.in_window(at(1), "21:00-01:00")
    assert not deploy.in_window(at(20, 59), "21:00-01:00")
    assert deploy.in_window(at(2), "01:00-05:00")
    assert not deploy.in_window(at(5), "01:00-05:00")


def test_the_hook_is_given_the_commit_as_ref(monkeypatch):
    sent = []

    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Answer())
    deploy.trigger(HOOK, MAIN)
    deploy.trigger("https://hook.test/deploy", MAIN)
    assert [(r.full_url, r.get_method(), r.data) for r in sent] == [
        (f"{HOOK}&ref={MAIN}", "POST", b""),
        (f"https://hook.test/deploy?ref={MAIN}", "POST", b""),
    ]


def test_a_request_carries_the_token_only_when_given(monkeypatch):
    sent = []

    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Answer())
    assert deploy.fetch_json("https://site.test/api/v1/version/") == {"commit": "x"}
    deploy.fetch_json("https://api.github.com/repos/owner/site/commits/main", "t")
    assert [r.get_header("Authorization") for r in sent] == [None, "Bearer t"]
    assert all(r.get_header("User-agent") == deploy.USER_AGENT for r in sent)
