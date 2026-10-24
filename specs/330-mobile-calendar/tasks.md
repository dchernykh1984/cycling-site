# Tasks: A calendar that reads on a phone

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/ui.md.
**Tests**: Required by constitution III. Checked items include original PR work verified in review;
unmarked items are remaining remediation, not claims about historical completion.

## Phase 1: Reconcile scope

- [x] T001 Record owner decisions and retrospective scope in specs/330-mobile-calendar/spec.md.
- [x] T002 Check all constitution principles in specs/330-mobile-calendar/plan.md.

## Phase 2: Existing shared foundations

- [x] T003 Verify shared period/chips/header partials in calendar_app/templates/calendar_app/.
- [x] T004 Verify visibility and date-window tests in calendar_app/tests.py.

## Phase 3: US1 - Read the phone calendar (P1)

Independent test: fresh phone opens days, Month opens grid, resize retains layout, multi-day event appears once.

- [x] T005 [US1] Add initial-layout and persistence regressions in tests/e2e/test_calendar_view.py.
- [x] T006 [US1] Select and retain phone layout in calendar_app/templates/calendar_app/calendar.html.
- [x] T007 [US1] Verify busy-day +N and multi-day rows in tests/e2e/test_calendar_busy_day.py and tests/e2e/test_calendar_phone_list.py.

## Phase 4: US2 - Retain and share selections (P1)

Independent test: reopen a selected weekend, then open an explicit floating current-month link.

- [x] T008 [US2] Add session/link precedence regressions in tests/e2e/test_period_nav.py.
- [x] T009 [US2] Resolve period before rendering in calendar_app/templates/calendar_app/calendar.html.
- [x] T010 [US2] Verify chip removal and filter-panel persistence in tests/e2e/test_filter_chips.py and tests/e2e/test_filter_toggle.py.

## Phase 5: US3 - Preserve facts and links (P1)

Independent test: phone row exposes city/sport, all remaining facts, Info and correct registration.

- [x] T011 [US3] Add metadata/link regressions in tests/e2e/test_calendar_phone_list.py.
- [x] T012 [US3] Restore event facts and Info in calendar_app/templates/calendar_app/list.html.

## Phase 6: US4 - Languages, places and access (P2)

Independent test: Kazakh range years first, settings override moves the empty map, picker focus returns.

- [x] T013 [P] [US4] Fix and verify year order in calendar_app/views.py and tests/e2e/test_period_nav.py.
- [x] T014 [P] [US4] Configure map fallback in cycling_site/settings/base.py and tests/test_map_home_area.py.
- [x] T015 [US4] Fix focus return and verify tests/e2e/test_period_nav.py.
- [x] T016 [US4] Fix wrapping/tap targets and verify tests/e2e/test_interface_rules.py and tests/e2e/test_filter_toggle.py.
- [x] T017 [US4] Keep new template source ASCII in calendar_app/templates/calendar_app/.

## Phase 7: Cross-cutting completion

- [ ] T018 Reconcile final behaviour and mirrored guidance in specs/site/calendar.md and .agents/skills/interface/SKILL.md.
- [ ] T019 Complete review cycles 2 and 3 and Spec Kit analysis in specs/330-mobile-calendar/review.md.
- [ ] T020 Run full unit/coverage and pre-commit checks described in specs/330-mobile-calendar/quickstart.md.
- [ ] T021 Refresh synthetic before/after report under tmp/pr343-review/ and verify final-head CI.

## Dependencies and parallel opportunities

T001-T004 precede remediation. US1 and US2 share calendar.html and must be sequential; US3 is
independent of them. T013 and T014 may be researched independently but both touch views.py, so
commits remain separate. US4's focus and tap regressions already passed. Final analysis follows all
four stories; final CI follows the last source commit.

## Delivery strategy

Retain the existing working foundations; first restore phone readability, then reliable selection,
then complete metadata and locale/configuration fixes. Validate every finding before committing it.
No merge and no production write are part of delivery.
