"""Before/after screenshots: does a branch still draw the light and dark themes as main does?

    python tests/visual/run.py --base-ref origin/main --out visual-out

Both sides run the same way, one after the other: a fresh database migrated by that side's code,
the same seed (tests/visual/seed.py from this checkout), the side's own server, the same capture
script and browser clock. The base side is a git worktree of --base-ref. Any pixel that differs,
outside the masks capture.py names, fails the run; the differences land in <out>/diff.

Needs a PostgreSQL server the current user can create databases on (--db-url names it).
"""

import argparse
import datetime
import itertools
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from urllib.parse import urlsplit, urlunsplit

import psycopg2

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture import DEVICES, capture  # noqa: E402
from compare import compare  # noqa: E402

REPO = HERE.parent.parent


def _with_db(url, name):
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _fresh_database(url, name):
    with closing(psycopg2.connect(_with_db(url, "postgres"))) as admin:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            cursor.execute(f'CREATE DATABASE "{name}"')
    return _with_db(url, name)


def _free_port():
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_up(url, process, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the server for {url} exited with {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=5)  # noqa: S310 -- our own server on 127.0.0.1
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"the server for {url} did not answer in {timeout}s")


def start_side(source, side, db_url, out, dump=None):
    """Migrate, seed and serve one side; return its address, the seed's description and the server."""
    side_out = out / side
    shutil.rmtree(side_out, ignore_errors=True)
    side_out.mkdir(parents=True)
    env = {
        **os.environ,
        "DATABASE_URL": _fresh_database(db_url, f"visual_{side}"),
        "DJANGO_SETTINGS_MODULE": "cycling_site.settings.test",
        "VISUAL_SESSIONS": str(side_out / "seed.json"),
    }
    # shortcut: both sides run in this checkout's environment; a branch that changes the
    # dependencies compares them against main's code on the new versions.
    manage = [sys.executable, "manage.py"]
    if dump:
        # Real content underneath the seed: a production backup (backup/<ts>/db.dump).
        subprocess.run(["pg_restore", "--no-acl", "--no-owner", f"--dbname={env['DATABASE_URL']}", dump], check=True)
    subprocess.run([*manage, "migrate", "-v0"], cwd=source, env=env, check=True)
    with (HERE / "seed.py").open() as seed:
        subprocess.run([*manage, "shell", "-v0"], cwd=source, env=env, stdin=seed, check=True)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [*manage, "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=source,
        env=env,
        stdout=(side_out / "server.log").open("w"),
        stderr=subprocess.STDOUT,
    )
    _wait_until_up(f"{base_url}/ru/", server)
    return base_url, json.loads((side_out / "seed.json").read_text()), server


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--out", default="visual-out", type=pathlib.Path)
    parser.add_argument("--db-url", default=os.environ.get("VISUAL_DB_URL", "postgres://localhost/postgres"))
    parser.add_argument("--devices", default=",".join(DEVICES))
    parser.add_argument("--cases", default="", help="comma-separated case names; all when empty")
    parser.add_argument("--dump", help="a pg_dump file to restore under the seed on both sides")
    parser.add_argument(
        "--approved",
        type=lambda value: value == "true",
        default=False,
        help="'true' lets differences through (the visual-change-approved label); errors still fail",
    )
    args = parser.parse_args()
    out = args.out.resolve()
    devices = tuple(args.devices.split(","))
    only = tuple(filter(None, args.cases.split(",")))

    base_source = out / "base-src"
    if base_source.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(base_source)], cwd=REPO, check=False)
    subprocess.run(["git", "worktree", "add", "--detach", str(base_source), args.base_ref], cwd=REPO, check=True)
    servers = []
    try:
        sides = {}
        for side, source in (("before", base_source), ("after", REPO)):
            *sides[side], server = start_side(source, side, args.db_url, out, args.dump)
            servers.append(server)
        if sides["before"][1]["today"] != sides["after"][1]["today"]:
            sys.exit("The day changed while the two sides were seeded; run again.")
        # One instant for every browser on both sides.
        now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
        problems, shots = _photograph_and_compare(sides, out, now, devices, only)
    finally:
        for server in servers:
            server.terminate()
            server.wait(timeout=30)
        subprocess.run(["git", "worktree", "remove", "--force", str(base_source)], cwd=REPO, check=False)

    sys.exit(report(problems, shots, out, args.approved))


def report(problems, shots, out, approved) -> int:
    """The exit code of a comparison that ran to the end.

    Only here can the label let anything through: a run that broke before comparing -- a failed
    migration, a page that did not load, content that was not there -- raises before this point and
    fails whatever the label says.
    """
    if not problems:
        print(f"All {shots} screenshots match.")
        return 0
    print(f"{len(problems)} of {shots} screenshots differ (pictures in {out / 'diff'}):")
    print("\n".join(f"  {problem}" for problem in problems))
    if approved:
        print("::warning::Light or dark changed; let through by the visual-change-approved label.")
        return 0
    return 1


# Chromium now and then rasterises text a few levels of grey apart (seen on the emulated Pixel 7),
# and a side can keep doing it shot after shot. Such a shot is taken again on both sides, and it
# matches when any take of the base equals any take of the branch, pixel for pixel. A real change is
# in every take of the branch, however small, so no pairing can hide it.
RETRIES = 3


def _photograph_and_compare(sides, out, now, devices, only):
    takes = {side: [out / side] for side in sides}
    for side, (base_url, data) in sides.items():
        capture(base_url, data, out / side, now, devices, only)
    shots = len(json.loads((out / "after" / "meta.json").read_text()))
    shutil.rmtree(out / "diff", ignore_errors=True)
    problems = compare(out / "before", out / "after", out / "diff")
    for attempt in range(1, RETRIES + 1):
        if not problems:
            break
        wanted = {problem.split(":")[0] for problem in problems}
        print(f"{len(wanted)} screenshots differ; taking them again (attempt {attempt} of {RETRIES}).")
        for side, (base_url, data) in sides.items():
            retry_dir = out / f"{side}-retry{attempt}"
            shutil.rmtree(retry_dir, ignore_errors=True)
            capture(base_url, data, retry_dir, now, devices, only, wanted)
            takes[side].append(retry_dir)
        unmatched = set(wanted)
        for before, after in itertools.product(takes["before"], takes["after"]):
            scratch = out / "diff-scratch"
            shutil.rmtree(scratch, ignore_errors=True)
            unmatched &= {problem.split(":")[0] for problem in compare(before, after, scratch, wanted)}
        shutil.rmtree(out / "diff", ignore_errors=True)
        latest = compare(takes["before"][-1], takes["after"][-1], out / "diff", unmatched)
        problems = latest
    return problems, shots


if __name__ == "__main__":
    main()
