# Specifications

The site is developed spec-first (issue #337): a feature is written down as a specification, then
planned, then built -- with [Spec Kit](https://github.com/github/spec-kit), whose skills both coding
agents in this repository (Claude Code and Codex) carry.

## What lives here

```
specs/
  site/                       the site as it works today, one file per area
    accounts.md  calendar.md  events.md  registrations.md  protocols.md  locations.md
    news-and-knowledge.md  site-shell.md  search-visibility.md  skins.md  api.md
    events-agents.md  audit.md  operations.md
  <issue>-<short-name>/       one feature, from its GitHub issue
    spec.md                   what and why, for the people who use it
    plan.md, research.md, data-model.md, contracts/, quickstart.md   how it will be built
    tasks.md                  the work, in order
    checklists/               optional quality checklists
```

The project's principles -- the "constitution" every plan is checked against -- are in
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

### `specs/site/`: the baseline

Each file describes one area as it behaves now: who does what (user stories with acceptance
scenarios), the functional requirements, the entities, the tests that pin it, the **local
assumptions** the code still makes (a place, a brand or a sport written into code -- see principle
VI), and open questions. They were written from the code and its tests; where something was not
clear it says so rather than guessing.

A local assumption marked **Accepted** is one the maintainer decided to keep; it is recorded so that
nobody "fixes" it again, and stays until they decide otherwise.

**Keep them true.** A change that alters an area's behaviour updates its file in the same pull
request: the scenario, the requirement, the tests line, and -- when it removes a hardcoded place or
sport -- the local assumptions.

### `specs/<issue>-<short-name>/`: a feature

A feature with its own GitHub issue gets a folder named after the issue -- for example
`specs/337-spec-driven-development/`, the issue that introduced all this. The number is the issue's,
so the spec, the branch (`337-spec-driven-development`) and the issue point at each other.

## The workflow

With Claude Code type the commands below; with Codex ask it to use the skill of the same name
(`speckit-specify`, `speckit-plan`, ...).

1. **Specify** -- `/speckit-specify SPECIFY_FEATURE_DIRECTORY=specs/<issue>-<short-name> <what the
   feature is for, in plain words>`. Name the directory yourself: left alone, Spec Kit numbers it
   on from the folders already here, not from the issue.
2. **Clarify** (optional) -- `/speckit-clarify` asks up to five pointed questions and writes the
   answers into the spec.
3. **Plan** -- `/speckit-plan` writes how it will be built and checks it against the constitution.
   The maintainer reviews the spec and the plan before any code is written.
4. **Tasks** -- `/speckit-tasks` turns the plan into ordered work; `/speckit-analyze` (optional)
   checks spec, plan and tasks against each other.
5. **Implement** -- `/speckit-implement` works through the tasks; `/speckit-converge` compares the
   code with the spec and adds what is still missing as tasks.
6. **Ship** -- the usual pull request, commits and review cycles (`shipping-changes` skill), with the
   feature's folder in it and the matching `specs/site/` files updated.

A bug fix or a small change needs no folder of its own, but still updates `specs/site/` when it
changes described behaviour.

## Spec Kit itself

Installed at version 1.2.2 for both agents: its skills are `.claude/skills/speckit-*` and
`.agents/skills/speckit-*`, its scripts and templates `.specify/`. Those files are Spec Kit's and are
kept out of the pre-commit hooks so that an upgrade can refresh them; do not edit them by hand. To
upgrade (needs [uv](https://docs.astral.sh/uv/)):

```
uvx --from specify-cli==<version> specify integration upgrade claude --script sh
uvx --from specify-cli==<version> specify integration upgrade codex --script sh
```

then review the diff like any other change.
