---
name: specs
description: Spec-driven development in this repository (issue #337) - where the specifications live, how a feature goes from issue to spec, plan, tasks and code with the Spec Kit skills, and how the baseline in specs/site/ is kept true. Read before starting a feature, and before changing behaviour any spec describes.
---

# Specifications

`specs/README.md` is the guide for people; this is what an agent needs on top of it.

## Where things are

- `.specify/memory/constitution.md` -- the principles every plan is checked against. Principle VI
  matters most day to day: **no local or sport-specific hardcoding**. The site began in Almaty, but
  places, sports, languages, time zones, map services, providers and brands are data or settings,
  never branches in the code. Examples the maintainer gives (a sport, a city, a race) explain an idea;
  they are not values to copy into code.
- `specs/site/<area>.md` -- the site as it works today, one file per area, each with the tests that
  pin it and its "Local assumptions".
- `specs/<issue>-<short-name>/` -- one feature: `spec.md`, then `plan.md` (+ research, data model,
  contracts, quickstart), then `tasks.md`.
- `.claude/skills/speckit-*`, `.agents/skills/speckit-*`, `.specify/` -- Spec Kit 1.2.2 itself.
  Generated, kept out of the pre-commit hooks, upgraded with `specify integration upgrade`; never
  edited by hand.

## A feature, from its issue

1. Read the issue and the `specs/site/` files of the areas it touches.
2. `speckit-specify` with `SPECIFY_FEATURE_DIRECTORY=specs/<issue>-<short-name>` -- name the folder
   after the issue yourself; Spec Kit would otherwise number it on from the folders already there.
   The branch is named the same way (`<issue>-<short-name>`).
3. `speckit-clarify` when the request leaves real choices open: put the questions to the maintainer
   (who writes in Russian) rather than guessing the answers.
4. `speckit-plan`; its Constitution Check must pass or justify each exception.
5. **Stop for review.** The maintainer reviews the spec and the plan (and may have another agent
   review them, with findings in a file such as `tmp/review.txt`) before any code is written.
6. `speckit-tasks`, optionally `speckit-analyze`, then `speckit-implement` -- still one atomic
   commit per change and the review cycles of `shipping-changes`.
7. Before the pull request: `speckit-converge` (or a read-through) to confirm the code matches the
   spec, and update the `specs/site/` files the feature changed.

A bug fix or a small change needs no folder of its own.

## Keeping `specs/site/` true

Any change -- feature, fix, refactor -- that alters behaviour a `specs/site/` file describes updates
that file in the same pull request: the scenario, the requirement, the tests line. A change that
touches code listed under "Local assumptions" removes the assumption (moving the value into data or
a setting) rather than adding another, and deletes the line. Write specs in English, ASCII, from the
code and tests -- never from memory -- and mark what is unknown `NEEDS CLARIFICATION`.
