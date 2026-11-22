"""Deploy main to the host when the site runs another commit and main is green (issue #153).

Run by .github/workflows/deploy.yml, at night and by hand. The site names the commit it runs at
/api/v1/version/; the host's deploy hook takes the commit to deploy as ``ref``. "Green" is every
workflow main's push of the commit started -- CI, the Dropbox check, any added later -- ending in
success (or skipped). A check still running is waited for; one that is red, or one that never
finishes, deploys nothing. A scheduled run that starts outside its window deploys nothing either:
the schedule asks for one every hour around the window, and the first inside it deploys. The run
then waits until the site names the new commit, so a deploy that fails or never starts turns the
workflow red instead of passing unseen.

Environment: GITHUB_REPOSITORY, GITHUB_TOKEN, SITE_BASE_URL, RENDER_DEPLOY_HOOK_URL, and for night
runs DEPLOY_WINDOW_UTC ("21:00-01:00": when a run may still deploy).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from datetime import time as clock

USER_AGENT = "UniversalBicycleTeam-Deploy/1.0"
CI_WORKFLOW = "ci.yml"
WAIT_SECONDS = 20 * 60
# how long main's checks may still run: CI takes about a quarter of an hour, the Dropbox check up to ten
# tries a minute apart
CHECKS_WAIT_SECONDS = 30 * 60
POLL_SECONDS = 20
GREEN = {"success", "skipped", "neutral"}

Fetch = Callable[[str, str], dict]


def fetch_json(url: str, token: str = "") -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def in_window(now: datetime, window: str) -> bool:
    """Whether ``now`` (UTC) falls in "HH:MM-HH:MM", a window that may cross midnight."""
    start, end = (clock.fromisoformat(part) for part in window.split("-"))
    moment = now.time()
    return start <= moment < end if start < end else moment >= start or moment < end


def live_commit(site: str, fetch: Fetch = fetch_json) -> str:
    """The commit the site says it runs, or "" when it cannot say (an older version, an outage)."""
    try:
        return str(fetch(f"{site}/api/v1/version/", "").get("commit") or "")
    except (OSError, ValueError):
        return ""


def main_checks(repo: str, sha: str, token: str, fetch: Fetch = fetch_json) -> dict[str, tuple[str, str]]:
    """Each workflow main's push of ``sha`` started, by its file: its name and how it ended ("" while it runs).

    Only push runs count: the agents and this deploy run on main's commit too, and are no check of it.
    The newest run of a workflow counts, so one started again counts by how it ended the last time.
    """
    query = urllib.parse.urlencode({"head_sha": sha, "event": "push", "branch": "main", "per_page": 100})
    runs = fetch(f"https://api.github.com/repos/{repo}/actions/runs?{query}", token).get("workflow_runs") or []
    checks: dict[str, tuple[str, str]] = {}
    for run in runs:  # newest first, as GitHub lists them
        workflow = str(run.get("path") or run.get("name") or "").split("@")[0].rsplit("/", 1)[-1]
        ended = str(run.get("conclusion") or "") if run.get("status") == "completed" else ""
        checks.setdefault(workflow, (str(run.get("name") or workflow), ended))
    return checks


def settled_checks(
    repo: str,
    sha: str,
    token: str,
    fetch: Fetch = fetch_json,
    sleep: Callable[[float], None] = time.sleep,
    seconds: int = CHECKS_WAIT_SECONDS,
) -> dict[str, tuple[str, str]]:
    """main's checks of ``sha``, waited for while any still runs -- or CI has not started -- and none is red."""
    checks = main_checks(repo, sha, token, fetch)
    for _ in range(seconds // POLL_SECONDS):
        conclusions = [conclusion for _name, conclusion in checks.values()]
        if any(c and c not in GREEN for c in conclusions) or (CI_WORKFLOW in checks and all(conclusions)):
            break
        sleep(POLL_SECONDS)
        checks = main_checks(repo, sha, token, fetch)
    return checks


def trigger(hook: str, sha: str) -> None:
    separator = "&" if "?" in hook else "?"
    # An empty body still sends "Content-Length: 0", which a server may require of a POST.
    request = urllib.request.Request(
        f"{hook}{separator}ref={sha}", data=b"", method="POST", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30):
        pass


def wait_until_live(
    site: str,
    sha: str,
    fetch: Fetch = fetch_json,
    sleep: Callable[[float], None] = time.sleep,
    seconds: int = WAIT_SECONDS,
) -> bool:
    for _ in range(seconds // POLL_SECONDS):
        sleep(POLL_SECONDS)
        if live_commit(site, fetch) == sha:
            return True
    return False


def run(
    env: dict[str, str],
    now: datetime,
    fetch: Fetch = fetch_json,
    deploy: Callable[[str, str], None] = trigger,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    window = env.get("DEPLOY_WINDOW_UTC", "")
    if window and not in_window(now, window):
        print(f"Started at {now:%H:%M} UTC, outside the window {window}: a run started inside it deploys.")
        return 0
    repo, token = env["GITHUB_REPOSITORY"], env.get("GITHUB_TOKEN", "")
    site = env["SITE_BASE_URL"].rstrip("/")
    sha = fetch(f"https://api.github.com/repos/{repo}/commits/main", token)["sha"]
    live = live_commit(site, fetch)
    if live == sha:
        print(f"The site already runs main ({sha[:8]}); nothing to deploy.")
        return 0
    checks = settled_checks(repo, sha, token, fetch, sleep)
    red = [f"{name} ({conclusion})" for name, conclusion in checks.values() if conclusion and conclusion not in GREEN]
    if red:
        print(f"::error::main ({sha[:8]}) is red: {', '.join(red)}; nothing deployed.")
        return 1
    running = [name for name, conclusion in checks.values() if not conclusion]
    if CI_WORKFLOW not in checks or running:
        minutes = CHECKS_WAIT_SECONDS // 60
        waited = ", ".join(running) if CI_WORKFLOW in checks else "CI has not started"
        print(f"::error::main's checks ({sha[:8]}) did not finish in {minutes} minutes: {waited}; nothing deployed.")
        return 1
    hook = env.get("RENDER_DEPLOY_HOOK_URL", "")
    if not hook:
        print("::error::The production environment's secret RENDER_DEPLOY_HOOK_URL is not set; nothing deployed.")
        return 1
    try:
        deploy(hook, sha)
    except OSError as error:  # said in words of our own: the hook's address carries its secret key
        answer = f"answered {error.code}" if isinstance(error, urllib.error.HTTPError) else "could not be reached"
        print(f"::error::The deploy hook {answer}; nothing deployed.")
        return 1
    print(f"Deploying {sha[:8]} over {live[:8] or 'an unnamed commit'}.")
    if wait_until_live(site, sha, fetch, sleep):
        print(f"The site runs {sha[:8]}.")
        return 0
    print(f"::error::The site does not name {sha[:8]} {WAIT_SECONDS // 60} minutes later; see the host's deploy log.")
    return 1


if __name__ == "__main__":
    sys.exit(run(dict(os.environ), datetime.now(UTC)))
