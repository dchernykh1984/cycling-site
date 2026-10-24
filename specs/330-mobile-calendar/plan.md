# Implementation Plan: A calendar that reads on a phone

**Branch**: `330-mobile-calendar` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

## Summary

Reconcile the existing PR with issue #330 and the constitution, then remediate the reviewed
behaviour in atomic commits. Use the existing FullCalendar list view for the initial phone
calendar, keep Month as the grid action, and preserve facts in the server-rendered List tab.
Resolve session state before rendering, with explicit incoming dates taking precedence.

This is retrospective planning for a PR started before Spec Kit. The maintainer has authorized
validation and repair of the review findings, delegated the phone default, and approved the PR's
light/dark styling. This does not claim pre-implementation approval of the original PR.

## Technical Context

**Language/Version**: Python 3.13 in CI (3.14 locally), Django 6, JavaScript and Django templates.
**Primary Dependencies**: Wagtail 7, Bootstrap 5.3, FullCalendar 6.1.15, Leaflet; existing skins.
**Storage**: Existing PostgreSQL event data; browser sessionStorage for view choices.
**Testing**: pytest/xdist, pytest-django, Playwright, pre-commit, CI coverage gate 90%.
**Target Platform**: Desktop browsers and phone browsers, including WebKit.
**Project Type**: Server-rendered web application with existing JSON endpoints.
**Performance Goals**: Reuse existing event queries and payloads; no new per-event HTTP requests.
**Constraints**: Three locales, ASCII UTF-8 source, no migrations or production writes; all CI green.
**Scale/Scope**: Three calendar views, ru/kk/en, light/dark/orange; existing pagination and visibility.

## Constitution Check

Checked before remediation planning and rechecked during final review:

| Principle | Design check |
| --- | --- |
| I Source facts | Render existing event facts; demo screenshots use explicitly synthetic fixtures. |
| II Owner decisions | No merge, production edits or paid agents; light/dark changes now approved. |
| III Tests | Regression tests accompany fixes; full unit, browser and CI checks gate completion. |
| IV Languages | Reuse translated labels and Django catalogues; Kazakh year order is explicit. |
| V Atomic completeness | One finding per commit; feature and baseline specifications reconciled. |
| VI Configuration | Home areas and empty-map fallback live in named settings, not template literals. |
| VII API | No new member data operation; existing events API and v1 permissions remain unchanged. |
| VIII One home | Existing model labels and shared date words supply UI; no duplicate taxonomy. |
| IX Data | No model change, migration, deletion or rewrite. |
| X Privacy | Existing query validation and visibility remain; shared URLs omit favorites. |
| XI Compatibility | No API field removed or made required. |
| XII Access | Focus return, named controls, usable taps, width and skin browser checks. |

The historical absence of a feature specification cannot be undone. It is documented here rather
than represented as a passing historical process gate. No ongoing exception is requested.

## Project Structure

```text
specs/330-mobile-calendar/
  spec.md
  plan.md
  research.md
  data-model.md
  contracts/ui.md
  quickstart.md
  checklists/requirements.md
  tasks.md
calendar_app/
  views.py
  templates/calendar_app/
cycling_site/settings/base.py
specs/site/calendar.md
tests/e2e/
tests/test_map_home_area.py
```

**Structure Decision**: Extend existing views and shared partials; use no new package or dependency.

## Complexity Tracking

No new abstraction, data store or permanent constitution exception is needed.
