# PR #343 review cycles

## Cycle 1 - Validate the initial review

The maintainer counted the initial review as cycle 1 and requested validation and atomic repairs.

| Finding | Validation and disposition |
| --- | --- |
| Missing feature artifacts and stale baseline | Confirmed by tracked paths and the 30-day baseline; spec/plan/tasks and baseline reconciled in e70dfb2. Historical pre-spec implementation is explicitly acknowledged. |
| Geographic fallback hardcoded in template | Confirmed in map.html; moved to MAP_DEFAULT_VIEW in 5b83b65. Seven map unit cases and an actual empty-map browser override passed. |
| Phone List loses facts and Info | Confirmed in the rendered row markup; restored existing model labels and links in b3f6b0d. Seven phone-list browser cases passed, including full facts and registration precedence. |
| Reopening loses selected period | Three regression cases failed before the fix; all 36 period tests passed after 37e2d03, including link priority and blocked storage. |
| Kazakh year order | Six period-label cases failed, then all 33 period tests passed after 05d6a27; backend year-order metadata is also tested. Narrowed: yearless day headings are valid and unchanged. |
| New non-ASCII template source | Confirmed on added lines; replaced comments, JS escapes and HTML entities in 1e38232 without changing rendered glyphs. |

Owner choices: a readable initial phone list, Month for the grid, and retained light/dark selection
styling are recorded in spec.md. The phone choice passed two failing-then-passing regressions and
16 calendar rendering cases after de13514.

Earlier obvious repairs are also retained: picker focus return (71173bc), POST-response waits in
album and locale tests (56ce718, 3df3408), navbar wrapping (b2bc5b6), and usable icon taps with a
WebKit-safe hit area (6031bbd, cd29053). The pushed cd29053 had all 12 CI checks successful.

Not treated as a new defect here: already-running events in bounded server lists are tracked in
#352; this PR does not change their date-overlap rule.

## Cycle 2 - Review the repaired diff

Read the full repaired production diff, shared partials, filter defaults, test allowances and
specifications. Three findings were accepted and repaired separately:

| Finding | Validation and fix |
| --- | --- |
| Filtered current-month calendar opens the whole season in List | Browser regression failed before repair; da12b48 makes the explicit month marker override the faceted default. Two backend cases and the browser transition passed. Plain faceted landing pages remain open-ended. |
| Month arrows replace the phone list with a grid | Browser regression failed before repair; cb44dae preserves the layout while stepping and after reopening. Month and month-picker actions still explicitly choose the grid. |
| New orange period-label defect is allowed as debt | Static comparison confirmed the exception covered a control introduced by this PR, contrary to FR-010. 82fd71d removes the allowance and uses 12px phone labels; all 45 language/width label cases passed in orange. Linux CI remains the final platform check. |

All 45 calendar/period browser cases passed after the repairs. No other actionable finding remained
in this pass.

## Cycle 3 - Final read-through

Reread the final source, tests and specification, including skin overrides (none replace these
calendar templates), data visibility, registration precedence, API compatibility, query reuse,
local settings and source encoding. Real browser inspection found English Mon..Sun headings in
the Kazakh grid. In 27fa66e the grid now uses Django's catalogue abbreviations, supplied by the
same date-word context as the period and day list. The new browser test failed for Kazakh before
the fix and passed for ru/kk/en afterwards. A visual check caught the abbreviation hook affecting
list headings; it was limited to the grid and a full-date regression was added. All 18 calendar
rendering and phone-list cases passed on WebKit/iPhone; an actual preview confirmed the
translated headings. The new Details disclosure also had less than a 44px target: a real edge-click
regression failed before its minimum height was corrected, then passed in Chromium and WebKit.

Spec Kit analysis found 12/12 functional requirements covered, 21 unique consecutive tasks, no
unresolved placeholders, no contradictory or duplicate requirements. One LOW task-label issue
(T013/T014 shared views.py despite parallel markers) was corrected. Final task/source read-through
found no remaining unbuilt feature work. The historical absence of pre-implementation review is
recorded in plan.md; it cannot be retroactively claimed to have happened.

Full local unit verification: 3025 passed plus 473 subtests, 97.17% coverage (90% gate).
All-file pre-commit passed after automatic formatting. The complete Chromium suite and the final
pushed-head CI are release gates; their final results and refreshed synthetic screenshots are
reported in the maintainer's external review report, not asserted in advance here.

## Requirement coverage

| Requirement | Tasks | Main evidence |
| --- | --- | --- |
| FR-001 | T005-T007 | calendar view, phone list and busy-day browser tests |
| FR-002 | T003, T008-T010 | period navigation and filtered-tab transition tests |
| FR-003 | T008-T009 | session restoration, explicit links and blocked-storage cases |
| FR-004 | T003, T010 | filter chips/toggle browser tests |
| FR-005 | T007 | multi-day and busy-day browser tests |
| FR-006 | T011-T012 | full facts, Info and registration precedence in phone rows |
| FR-007 | T004, T008-T009 | baseline date defaults and explicit-month backend tests |
| FR-008 | T014 | map unit cases and actual fallback override browser case |
| FR-009 | T013 | date words, year order and three-locale grid browser cases |
| FR-010 | T015-T016, T020 | picker focus, actual tap and all-skin interface checks |
| FR-011 | T004, T020 | full unit/API/visibility/registration suite; no migrations |
| FR-012 | T001-T002, T017-T019 | artifact analysis, mirrored guidance and encoding hooks |

All twelve constitution principles have a design check in plan.md. No production data was changed,
no paid workflow was run and this PR must remain unmerged until the maintainer asks.

## Post-review CI validation

At head 89ff162, eleven checks succeeded and desktop WebKit exposed an inherited live-protocol
test race. Its only poll had already started before routing was installed, returned the final
version, and finished live without exercising a stalled request; the trace showed that response
and the test's empty `stalled` list. The no-op `wait_for_function("() => true")` was not a wait.

The test now installs interception before opening the page and keeps metadata requests unanswered
until an actual timeout warning is observed. Only then does it publish the final version and let
future requests through. Keeping the warning observable avoids a second race where a successful
retry hides it before the assertion polls. All eight live-protocol cases passed on desktop WebKit
and all eight on WebKit/iPhone. This is test synchronization only; production polling is unchanged.
The full pipeline must be checked again at the new pushed head before the owner's requested admin
rebase merge.
