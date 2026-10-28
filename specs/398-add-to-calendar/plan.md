# Implementation Plan: Add an event to the reader's own calendar

**Branch**: `398-add-to-calendar` | **Spec**: [spec.md](spec.md)

## Summary

One address beside the subscription: `/<lang>/calendar/<id>/event.ics`, the one event, built by the
subscription's `build_calendar`. A link beside the share button, looking like it, leads to that
file. The API serves the same file.

## Constitution Check

- **II (the maintainer's decisions)**: light and dark draw the button as they draw "Share"
  (`btn-outline-secondary`). In light that carries the share button's known contrast shortfall
  (2.8:1 at rest, `tests/e2e/test_skin_contrast.py`); changing it changes light, which is the
  maintainer's; they had both darkened to 4.5:1 in issue #383. The orange skin already draws the two alike; a browser test compares their colours
  in whichever skin the suite runs in.
- **IV (language)**: the button and the file speak the page's language; the API takes
  `lang` from the site's languages.
- **VI (anywhere)**: the file is the iCalendar standard, no provider is named. Nothing is added to
  "Local assumptions".
- **VII (API)**: `GET /api/v1/competitions/{id}/ics`.
- **VIII (one fact, one home)**: one builder for the subscription and the file; one rule
  (`can_open`) for the page and the file.
- **XI (API promises)**: a new endpoint only.
- **XII (any screen)**: 44 px on a phone, words with the icon.

## Design

1. `calendar_app/visibility.can_open`: the page's rule, taken out of `CompetitionDetailView` so the
   file follows it too.
2. `calendar_app/feeds.py`: `CompetitionEventICSView` at `<id>/event.ics`; `_event_lines` adds a
   `GEO` line for a venue's own point (`locations.maps.start_point`), so the subscription carries it
   too.
3. `cycling_site/templates/_calendar_button.html`, included by `calendar_app/detail.html` beside
   "Share" for a published event: a link to the file, drawn as the share button is.
4. `api/endpoints/competitions.py`: `GET /{id}/ics`, under `_require_visible_or_404`.
