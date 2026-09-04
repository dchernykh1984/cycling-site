# cycling-site

A calendar of endurance-sport events -- cycling, running, skiing, hiking -- across Kazakhstan,
Kyrgyzstan, Russia and beyond, with a knowledge base, news, race registration, refereeing and live
protocols. Django 6 + Wagtail, three locales (ru / kk / en), deployed on Render at
universalbicycle.team.

## Rules that are not negotiable

- **Never merge a pull request** unless the maintainer asks for it in the message you are answering.
  Drive the pipeline green and stop.
- **Never run an events agent** (`agent.yml`, `telegram-agent.yml`, `instagram-agent.yml`) without
  being asked: every run spends money on the LLM provider.
- **Never invent facts.** Announcements, articles and event data carry only what the source says.
  When a source is contradictory, transcribe it and say so rather than tidying it into a guess.
- **Approved events belong to the maintainer.** A cleanup that would change one -- its links, its
  location, its dates -- needs their explicit go-ahead first.
- Commit messages are **one line**, no body, and never mention Claude or co-authorship.
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

## Quick facts

- Tests: `.venv/bin/python -m pytest -n 10` (xdist; a serial run is too slow to iterate on).
  End-to-end Playwright tests live in `tests/e2e/` and are excluded by default.
- Lint and format: `ruff` via pre-commit; `mypy` runs there too.
- Every reader-facing URL carries a language prefix (`/ru/`, `/kk/`, `/en/`); machine-facing ones
  (`/api/v1/`, admin, media, sitemap, robots) do not.
