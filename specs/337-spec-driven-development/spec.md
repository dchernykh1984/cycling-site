# Feature Specification: Spec-driven development with Spec Kit

**Feature Branch**: `337-spec-driven-development`
**Created**: 2026-10-21
**Status**: Implemented (pull request for issue #337)
**Input**: Issue #337 -- "Add spec-kit, so that development is spec-driven with AI assistants." The
maintainer added: put every current specification into it; describe it for people and for agents;
the constitution must forbid local and sport-specific hardcoding; review cycles as usual.

## User Scenarios & Testing

### User Story 1 - Start a feature from a specification (Priority: P1)

The maintainer files an issue; an agent (Claude Code or Codex) writes the feature's specification
and plan in `specs/<issue>-<name>/` with the Spec Kit skills, and the maintainer reviews them before
any code is written.

**Why this priority**: it is the point of the issue -- agreeing on what to build before building it.

**Independent Test**: ask either agent for `speckit-specify` with
`SPECIFY_FEATURE_DIRECTORY=specs/<issue>-<name>`; a `spec.md` appears there, filled from the
template, and `speckit-plan` adds a plan with a Constitution Check.

**Acceptance Scenarios**:

1. **Given** Claude Code, **When** the maintainer types `/speckit-specify ...`, **Then** the skill is
   found in `.claude/skills/speckit-specify/` and writes the spec.
2. **Given** Codex, **When** asked to use the `speckit-specify` skill, **Then** it is found in
   `.agents/skills/speckit-specify/` and behaves the same.

### User Story 2 - Know what the site does today (Priority: P1)

Anyone -- a person or an agent -- can read how each area of the site behaves now, which tests pin it,
and which local assumptions the code still makes.

**Why this priority**: a new feature is specified against what exists; without a baseline every spec
starts from a guess.

**Independent Test**: open `specs/site/`; every area has a file with scenarios, requirements, the
code and tests that implement it, local assumptions and open questions.

**Acceptance Scenarios**:

1. **Given** `specs/site/`, **Then** it covers accounts, calendar, events, registrations, protocols,
   locations, news and knowledge, the site shell, search visibility, skins, the API, the events
   agents, the audit log and operations.
2. **Given** a spec names code or tests that are renamed or removed, **Then** `tests/test_specs.py`
   fails and says which.

### User Story 3 - Principles every plan is held to (Priority: P2)

**Acceptance Scenarios**:

1. **Given** `.specify/memory/constitution.md`, **Then** it states the project's standing rules and
   principle VI: places, sports, languages, time zones, map services and brands are data or settings,
   never written into code; examples explain, they are not values to copy.

### Edge Cases

- Spec Kit's own files carry typographic punctuation and are refreshed by `specify integration
  upgrade`, which keeps any file it finds edited: the pre-commit hooks leave them alone, while the
  constitution and every spec are checked like any file.
- Spec Kit numbers a new spec folder on from the existing ones; the folder is named after the issue
  explicitly instead.

## Requirements

### Functional Requirements

- **FR-001**: Spec Kit 1.2.2 is installed for Claude Code and for Codex, with shell scripts.
- **FR-002**: The constitution states principles I-VI and governs plans.
- **FR-003**: `specs/site/` describes the whole site as it works today, in English, from the code
  and tests, each file with a "Local assumptions" section.
- **FR-004**: People are told how to work with specs (`README.md`, `specs/README.md`); agents through
  the `specs` skill (both copies), the tables in `CLAUDE.md` / `AGENTS.md`, and the
  `shipping-changes` and `working-with-the-maintainer` skills.
- **FR-005**: Pull requests and feature requests ask for their specifications.
- **FR-006**: A test keeps the baseline's sections and named paths true.

### Key Entities

- **Constitution**, **baseline spec** (`specs/site/<area>.md`), **feature spec folder**
  (`specs/<issue>-<name>/`).

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every area of the site has a baseline spec (14 files) and the guard test passes.
- **SC-002**: Both agents list the Spec Kit skills and the `specs` skill.
- **SC-003**: The next feature issue is specified, planned and reviewed in `specs/<issue>-<name>/`
  before code.

## Assumptions

- The baseline describes behaviour as of `main` on 2026-10-21; later changes keep it current.
- Removing the local assumptions it lists is future work, done as the code they sit in is touched.
