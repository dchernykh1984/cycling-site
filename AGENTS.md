# cycling-site

A platform that helps people organize sport and the activities around it wherever people move --
cycling, running, skiing, hiking and more: announcing an event, registration, timing and live
protocols, with a knowledge base and news. It began in Almaty and is meant for anyone, anywhere.
Django 6 + Wagtail, three locales (ru / kk / en), deployed on Render at universalbicycle.team.

## Rules that are not negotiable

- **Never merge a pull request** unless the maintainer asks for it in the message you are answering.
  Drive the pipeline green and stop.
- **Never run an events agent** (`agent.yml`, `telegram-agent.yml`, `instagram-agent.yml`) without
  being asked: every run spends money on the LLM provider.
- **Never invent facts.** Announcements, articles and event data carry only what the source says.
  When a source is contradictory, transcribe it and say so rather than tidying it into a guess.
- **Localize reader-facing data fields by default.** Names, titles, captions and descriptions
  have ru / kk / en values. A document such as a knowledge article may instead belong to one
  locale and appear only in that locale's listings. IDs, dates, numbers and URLs are not translated.
- **An API by default.** What a participant or an organizer reads or changes on the site is also
  available through `/api/v1/`, with the site's permission rules; a new feature ships its API
  operations and their tests. What is still missing is listed under "API gaps" in `specs/site/`.
- **Approved events belong to the maintainer.** A cleanup that would change one -- its links, its
  location, its dates -- needs their explicit go-ahead first.
- Commit messages are **one line**, no body, and never mention Codex or co-authorship.
- Source files are **ASCII only** (a pre-commit hook enforces it for python, markdown, yaml, toml,
  shell and json). Russian belongs in translation catalogues and in the agents' guidance files.
- Write files as **UTF-8**. A PowerShell redirect, `Set-Content` or `Out-File` defaults to UTF-16,
  and the ASCII hook then rejects a file whose text looks perfectly plain in an editor -- the bytes
  are the problem, not the characters. `file <path>` says which encoding you actually wrote.

## Where the details live

| Skill | What it covers |
| --- | --- |
| `working-with-the-maintainer` | how they work, what to ask first, what the default task shape is |
| `shipping-changes` | branches, commits, review cycles, the pipeline, what CI runs |
| `site-content` | publishing and editing articles, news and events on the live site |
| `production-access` | reaching production: shell, database, media, logs |
| `events-agents` | the three import agents, their schedules, their logs |
| `calendar-curation` | filling and fixing the calendar by hand |
| `locations` | the four-level geography tree and the rules that keep it clean |
| `translations` | three locales, gettext, and the traps in this repo |
| `search-visibility` | per-language URLs, sitemap, structured data, feeds, IndexNow |
| `protocols` | how a results file is served, and what may appear inside one |
| `skins` | the look of the site: light and dark kept as they are, designers' skins, their checks |
| `specs` | spec-driven development: the constitution, `specs/site/`, a feature from issue to spec, plan and code |
| `interface` | how a page should look and behave -- phone first, nothing that jumps, qualities and patterns of the look, tap targets, fit, contrast -- and its checks |

## Quick facts

- Tests: `.venv/bin/python -m pytest -n 10` (xdist; a serial run is too slow to iterate on).
  End-to-end Playwright tests live in `tests/e2e/` and are excluded by default.
- Lint and format: `ruff` via pre-commit; `mypy` runs there too.
- Every reader-facing URL carries a language prefix (`/ru/`, `/kk/`, `/en/`); machine-facing ones
  (`/api/v1/`, admin, media, sitemap, robots) do not.

## Coding agent context

Codex reads this file at startup. The skills named in the table above are files:
`.agents/skills/<name>/SKILL.md`. Read the one that covers the task before starting it --
nothing loads them automatically.

Claude keeps the same guidance under `CLAUDE.md` and `.claude/skills/`, byte for byte apart
from the agent's own name. A convention that changes has to change in both, or the next
session with the other tool works from the old rules.

`.codex/hooks.json` runs `.codex/hooks/post_edit.py` after `apply_patch` (and after a plain
editor tool): it formats edited Python with `ruff` and reports non-ASCII bytes using the same
patterns as the pre-commit gate, kept in `.codex/hooks/checks.json`. It reports a finished
edit rather than preventing one, and a file written straight from the shell never reaches it --
only the commit gate catches that. Its tests live in `tests/test_codex_hook.py`, because
pytest does not look inside a directory whose name starts with a dot.
