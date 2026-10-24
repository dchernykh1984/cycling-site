# Verification

Use a local scratch database. Do not run the paid events workflows.

1. Run `.venv/bin/python -m pytest -n 10 -q --ignore=tests/e2e` and verify coverage >=90%.
2. Run `.venv/bin/python -m pytest tests/e2e/test_calendar_view.py tests/e2e/test_period_nav.py tests/e2e/test_calendar_phone_list.py tests/e2e/test_calendar_map.py tests/e2e/test_filter_toggle.py tests/e2e/test_filter_chips.py -n 4 -q`.
3. Run `pre-commit run --all-files` and the Spec Kit prerequisite/analysis checks.
4. Open a fresh phone calendar, choose Month, resize, reopen it, and follow List/Map links.
5. Inspect ru/kk/en, all skins, mobile facts, keyboard picker focus and before/after demo screenshots.

Use a separate `DATABASE_URL` for concurrent suites. The pipeline must complete successfully at the
final pushed SHA: unit coverage, pre-commit, commitizen, audit, five browser/device jobs and all skins.
Do not merge the PR.
