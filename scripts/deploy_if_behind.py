"""Deploy main to the host when the site runs another commit and main's CI passed (issue #153).

Run by .github/workflows/deploy.yml, at night and by hand. The site names the commit it runs at
/api/v1/version/; the host's deploy hook takes the commit to deploy as ``ref``. Nothing is deployed
while main's CI is red or unfinished, a night run that starts after its window waits for the next
night, and the run waits until the site names the new commit -- so a deploy that fails or never
starts turns the workflow red instead of passing unseen.

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
POLL_SECONDS = 20

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


def ci_conclusion(repo: str, sha: str, token: str, fetch: Fetch = fetch_json) -> str:
    """How CI on main's push of ``sha`` ended -- "success", "failure", ... -- or "" while it runs."""
    query = urllib.parse.urlencode({"head_sha": sha, "event": "push", "branch": "main"})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{CI_WORKFLOW}/runs?{query}"
    runs = fetch(url, token).get("workflow_runs") or []
    return (runs[0].get("conclusion") or "") if runs else ""


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
        print(f"Started at {now:%H:%M} UTC, outside the window {window}: the next night deploys.")
        return 0
    repo, token = env["GITHUB_REPOSITORY"], env.get("GITHUB_TOKEN", "")
    site = env["SITE_BASE_URL"].rstrip("/")
    sha = fetch(f"https://api.github.com/repos/{repo}/commits/main", token)["sha"]
    live = live_commit(site, fetch)
    if live == sha:
        print(f"The site already runs main ({sha[:8]}); nothing to deploy.")
        return 0
    conclusion = ci_conclusion(repo, sha, token, fetch)
    if conclusion != "success":
        print(f"::error::CI on main ({sha[:8]}) is {conclusion or 'not finished'}; nothing deployed.")
        return 1
    hook = env.get("RENDER_DEPLOY_HOOK_URL", "")
    if not hook:
        print("::error::The repository secret RENDER_DEPLOY_HOOK_URL is not set; nothing deployed.")
        return 1
    try:
        deploy(hook, sha)
    except urllib.error.HTTPError as error:  # its text never carries the hook's secret address
        print(f"::error::The deploy hook answered {error.code}; nothing deployed.")
        return 1
    print(f"Deploying {sha[:8]} over {live[:8] or 'an unnamed commit'}.")
    if wait_until_live(site, sha, fetch, sleep):
        print(f"The site runs {sha[:8]}.")
        return 0
    print(f"::error::The site does not name {sha[:8]} {WAIT_SECONDS // 60} minutes later; see the host's deploy log.")
    return 1


if __name__ == "__main__":
    sys.exit(run(dict(os.environ), datetime.now(UTC)))
