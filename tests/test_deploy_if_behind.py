"""The nightly deploy deploys main only when the site runs another commit and main's CI passed (#153)."""

import urllib.error
from datetime import UTC, datetime
from urllib.parse import parse_qs

from scripts import deploy_if_behind as deploy

MAIN, OLD = "a" * 40, "b" * 40
HOOK = "https://api.render.com/deploy/srv-x?key=secret"
ENV = {"GITHUB_REPOSITORY": "owner/site", "GITHUB_TOKEN": "t", "SITE_BASE_URL": "https://site.test/"}
NIGHT = datetime(2026, 11, 19, 21, 7, tzinfo=UTC)


class Site:
    """GitHub and the site as the script sees them; a deploy makes the site name main."""

    def __init__(self, live=OLD, conclusion="success", runs=True, answers=True, takes=True):
        self.live, self.conclusion, self.runs, self.answers, self.takes = live, conclusion, runs, answers, takes
        self.deployed: list[tuple[str, str]] = []

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
        assert path.endswith("/actions/workflows/ci.yml/runs"), url
        assert parse_qs(query) == {"head_sha": [MAIN], "event": ["push"], "branch": ["main"]}, "main's own CI"
        return {"workflow_runs": [{"conclusion": self.conclusion}] if self.runs else []}

    def deploy(self, hook, sha):
        self.deployed.append((hook, sha))
        if self.takes:
            self.live, self.answers = sha, True

    def run(self, env=None, now=NIGHT):
        return deploy.run(
            {**ENV, "RENDER_DEPLOY_HOOK_URL": HOOK, **(env or {})}, now, self.fetch, self.deploy, lambda s: None
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


def test_a_red_or_unfinished_ci_deploys_nothing():
    for site in (Site(conclusion="failure"), Site(conclusion=None), Site(runs=False)):
        assert site.run() == 1
        assert site.deployed == []


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


def test_a_night_run_started_after_its_window_waits_for_the_next_night():
    site = Site()
    late = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)
    assert site.run({"DEPLOY_WINDOW_UTC": "21:00-01:00"}, now=late) == 0
    assert site.deployed == []
    assert site.run({"DEPLOY_WINDOW_UTC": "21:00-01:00"}) == 0
    assert site.deployed == [(HOOK, MAIN)]


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

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Answer())
    deploy.trigger(HOOK, MAIN)
    deploy.trigger("https://hook.test/deploy", MAIN)
    assert [(r.full_url, r.get_method(), r.data) for r in sent] == [
        (f"{HOOK}&ref={MAIN}", "POST", b""),
        (f"https://hook.test/deploy?ref={MAIN}", "POST", b""),
    ]


def test_a_request_carries_the_token_only_when_given(monkeypatch):
    sent = []

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"commit": "x"}'

    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Answer())
    assert deploy.fetch_json("https://site.test/api/v1/version/") == {"commit": "x"}
    deploy.fetch_json("https://api.github.com/repos/owner/site/commits/main", "t")
    assert [r.get_header("Authorization") for r in sent] == [None, "Bearer t"]
    assert all(r.get_header("User-agent") == deploy.USER_AGENT for r in sent)
