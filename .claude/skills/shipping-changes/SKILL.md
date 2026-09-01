---
name: shipping-changes
description: How work reaches main in this repository - branches, atomic commits, the review cycles the maintainer expects, and the CI that has to go green. Read before starting any code change.
---

# Shipping a change

## One branch per task, tied to a ticket when there is one

Branch from an up-to-date `main`. Name it after the issue when the work has one
(`275-seo-indexing`), otherwise after the change (`fix/agent-announcement-links`). The maintainer
sometimes says "no ticket needed, just a branch" -- then skip the issue and put the analysis into
the pull request body instead.

Several unrelated tasks may share one pull request when the maintainer asks for it: merging puts the
site down for a few minutes, so they batch. Each task still gets its own commit.

## Commits

- **One commit per atomic change.** A task, a fix, a review finding -- each is its own commit.
- **Single line, no body.** No `Co-Authored-By`, no mention of Claude anywhere.
- Types come from commitizen: `build|bump|chore|ci|docs|feat|fix|perf|refactor|revert|style|test`.
  There is no `i18n` type -- translation work is `feat` or `fix` on the area it serves.
- Write what the change does for a reader, not what you edited: `fix(agent): link the post an event
  was announced in`, not `update run.py`.
- pre-commit reformats on commit and then fails; run the same `git commit` again and it passes.

## Review cycles

Three cycles is the default for a task unless the maintainer says otherwise. A cycle is: read your
own diff as if someone else wrote it, and for each finding you agree with, make a **separate**
commit that fixes it. Findings you disagree with are worth saying out loud rather than silently
skipping.

Look for: a case the code gets wrong (nulls, ordering, empty input), behaviour that contradicts the
docstring, a test that asserts the implementation rather than the behaviour, and duplication that
already has a home elsewhere.

## The pipeline

`ci.yml` runs pre-commit (ruff, mypy, ASCII check, requirements export), commitizen, the unit tests
with coverage (the gate is 90%), and a dependency audit. `e2e.yml` runs Playwright on five
browser/device combinations. All nine checks must be green before you report the work done.

Locally: `.venv/bin/python -m pytest -n 10 -q --ignore=tests/e2e` for the unit suite, and
`.venv/bin/python -m pytest tests/e2e -q` when the change touches templates or JavaScript.

A red `audit` job usually means a new CVE in a dependency rather than anything you wrote: bump the
patch release (`uv lock --upgrade-package "django==6.0.8"`), re-export requirements, run the suite.

## Every change carries its tests

A bug fix gets a regression test that fails without the fix: a Django unit test for backend
behaviour, a Playwright test in `tests/e2e/` for anything a person sees in a browser. Name tests
after the behaviour, not the function.

## Opening the pull request

`gh pr create --base main` with a body that explains what was wrong, what changed, and what is
deliberately out of scope. Say what you measured rather than what you assume.

Then **stop**. Merging is the maintainer's; when they do merge, it is `--rebase` so every commit
survives and the history stays linear.
