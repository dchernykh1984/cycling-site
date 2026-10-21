<!--
Sync Impact Report
- Version: none -> 1.0.0 (first constitution, issue #337)
- Principles: all added, drawn from CLAUDE.md / AGENTS.md and the skills under .claude/skills
  and .agents/skills, which stay the detailed runtime guidance.
- Templates: plan-template.md's "Constitution Check" gate reads these principles; no template
  needed changes.
-->

# cycling-site Constitution

cycling-site is a calendar of endurance-sport events -- cycling, running, skiing, hiking --
across Kazakhstan, Kyrgyzstan, Russia and beyond, with a knowledge base, news, race registration,
refereeing and live protocols, served at universalbicycle.team in Russian, Kazakh and English.

## Core Principles

### I. Facts come from their source

Announcements, articles and event data carry only what their source says. When a source is
contradictory, it is transcribed and the contradiction named, never tidied into a guess.
Coordinates and venues are looked up, never recalled from memory. A specification describes the
behaviour the code and its tests show; where that is unknown, it says so (`NEEDS CLARIFICATION`)
rather than inventing it.

### II. Some decisions belong to the maintainer

Only the maintainer merges a pull request, and only when asked in the message being answered.
Approved events are theirs: changing one -- its links, location or dates -- needs their explicit
go-ahead. The events agents spend money on every run and are started only on request. The light
and dark themes are kept as they are; a deliberate change to them passes only with the
`visual-change-approved` label, which the maintainer sets.

### III. Every change carries its tests (NON-NEGOTIABLE)

A behaviour change ships with the tests that pin it: a Django unit test for backend behaviour, a
Playwright test under `tests/e2e/` for anything a person sees in a browser. A bug fix gets a
regression test that fails without the fix. Tests are named after the behaviour, not the function.
Coverage stays at 90% or above, and every check of the pipeline -- unit tests, pre-commit, the
browser suite on five browsers and devices and once per skin, the light/dark screenshot comparison,
the dependency audit -- is green before work is reported done.

### IV. Three languages, every reader's address in one

Everything a reader sees exists in Russian, Kazakh and English. Every reader-facing URL carries
its language prefix (`/ru/`, `/kk/`, `/en/`); machine-facing ones (`/api/v1/`, admin, media,
sitemap, robots) do not. Source files are ASCII and UTF-8; Russian and Kazakh text lives in the
translation catalogues and in the agents' guidance files.

### V. Small, complete, reviewable changes

Each atomic change is one commit with a one-line message in the commitizen types, never
mentioning the assistant that wrote it. Work is reviewed in cycles -- three by default -- each
finding fixed in a commit of its own. Pull requests are merged by rebase so every commit survives
on a linear history. A change finishes every part it touches -- callers, tests, translations,
setup hints, documentation, specifications -- and adds nothing nobody asked for.

## Constraints

- Stack: Django 6 with Wagtail 7, PostgreSQL, Bootstrap 5.3 with the Bootswatch Lux theme,
  Python 3.13 (CI), dependencies locked with uv and exported to `requirements.txt`.
- Hosting: Render, behind Cloudflare. Production data is restored locally only into scratch
  databases.
- The look of the site is split into skins (`skins/`): designers own their skins; a change to the
  site that breaks a skin does not merge until the skin is green again.

## Development Workflow

- A feature with its own GitHub issue gets a specification in `specs/<issue>-<short-name>/`
  (`spec.md`, then `plan.md` and `tasks.md`), made with the Spec Kit skills (`/speckit-specify`,
  `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze`, `/speckit-implement`).
  The maintainer reviews the specification and the plan before implementation starts.
- `specs/site/` describes the site as it works today, one file per area. A change that alters an
  area's behaviour updates its file in the same pull request.
- A bug fix or a small change needs no specification of its own, but still updates `specs/site/`
  when it changes described behaviour.

## Governance

This constitution states the principles; `CLAUDE.md`, `AGENTS.md` and the skills they list hold
the detail and are kept consistent with it. The maintainer amends it through a pull request that
bumps the version -- MAJOR for a principle removed or redefined, MINOR for one added or materially
expanded, PATCH for wording -- and updates the Last Amended date. Plans check themselves against
it in their "Constitution Check".

**Version**: 1.0.0 | **Ratified**: 2026-10-21 | **Last Amended**: 2026-10-21
