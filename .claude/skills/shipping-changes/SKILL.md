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

For a new field a person fills in, also ask who reads it before readers do (a moderator who never
sees it cannot reject it), and what each locale shows when only one was filled; then check that
the form's hint text says what the tests pin.

After a set of cycles, report them as a table, to the maintainer and in the pull request's body:
one row per cycle with how many findings it fixed, how many of each severity and the most notable
one, and a last row that adds them up. A cycle that found nothing is a row of zeros, not a missing
row -- it shows the review running dry. High: data lost or exposed, a page or the pipeline broken.
Medium: wrong behaviour a person meets. Low: rough edges, wording, speed.

| Cycle | Findings | High | Medium | Low | Most notable |
| --- | --- | --- | --- | --- | --- |
| 1 | 3 | 0 | 1 | 2 | two members finishing together could both be first |
| **All** | 3 | 0 | 1 | 2 | |

## The pipeline

`ci.yml` runs pre-commit (ruff, mypy, ASCII check, requirements export), commitizen, the unit tests
with coverage (the gate is 90%), and a dependency audit. `e2e.yml` runs Playwright on five
browser/device combinations, and once more in desktop Chromium for every skin under `skins/` but
light (`E2E_SKIN`). Every check must be green before you report the work done.

A change to the site that breaks a designer's skin -- its `e2e-skin (<key>)` job goes red -- does
not merge until that skin is green: the pull request waits for the skin's designers, or fixes the
skin itself (`skins/<key>/`) in a commit of its own.

Read that verdict from the rollup rather than from `gh pr checks`. The per-check status the latter
reports lags, and can still say `pending` long after a job has finished -- on a pipeline this wide
that reads like a hung check, and waiting on it wastes the time it appears to be saving:

```bash
gh pr view <n> --json statusCheckRollup \
  --jq '[.statusCheckRollup[] | {name:(.name//.context), s:(.conclusion//.state)}]'
```

Locally: `.venv/bin/python -m pytest -n 10 -q --ignore=tests/e2e` for the unit suite, and
`.venv/bin/python -m pytest tests/e2e -q` when the change touches templates or JavaScript.

A red `audit` job usually means a new CVE in a dependency rather than anything you wrote: bump the
patch release (`uv lock --upgrade-package "django==6.0.8"`), re-export requirements, run the suite.

## Migrations

A model change needs `makemigrations`, the migration committed with the change, and a moment's
thought about whether it is safe on live data. `manage.py makemigrations --check --dry-run` is what
CI effectively asks; run it before opening the pull request.

## Every change carries its tests

A bug fix gets a regression test that fails without the fix: a Django unit test for backend
behaviour, a Playwright test in `tests/e2e/` for anything a person sees in a browser. Name tests
after the behaviour, not the function.

## Specifications stay current

A change that alters behaviour described in `specs/site/` updates that file in the same pull request;
a feature with its own issue carries its `specs/<issue>-<name>/` folder. Review cycles check both,
and check that nothing local or sport-specific was written into the code (constitution, principle
VI). See the `specs` skill.

## Setup hints stay current

The line under the menu that tells a reader what to set up (`cycling_site/setup_hints.py`, issue
#319) is part of a feature, not decoration. When a change:

- **makes a feature depend on something the member sets up** -- a new preference, new profile data,
  a new sign-in requirement -- add a hint for it, in its place in the order, with its translations
  and a test;
- **removes such a dependency, moves the setting, or changes how "set up" is checked** -- update or
  remove the hint in the same pull request.

Hints are about setting the site up, one at a time. They are not a channel for announcing new
features: a line that changes every week gets closed by reflex, which defeats the ones that matter.

## Opening the pull request

`gh pr create --base main` with a body that explains what was wrong, what changed, and what is
deliberately out of scope. Say what you measured rather than what you assume.

Then **stop**. Merging is the maintainer's; when they do merge, it is `--rebase` so every commit
survives and the history stays linear.
