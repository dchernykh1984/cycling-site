# Research and decisions

- **Phone default**: Use FullCalendar's existing `listRange` below the existing 992px breakpoint.
  Month explicitly opens the grid. This satisfies #330 without a second navigation bar; retain the
  chosen layout for the visit and do not switch it when the window is resized. The maintainer
  delegated this choice on 2026-10-24. Alternative: always-grid made phone titles hard to read.
- **Session precedence**: Read the incoming URL before FullCalendar's first `datesSet` can write
  storage. Dates in the URL win; `period=month` explicitly selects the floating current month;
  only a URL without a period selection can restore stored dates. Sharing a month must not pin
  today's date. Alternative: bare month links conflict with restoring an earlier session range.
- **Kazakh dates**: Inspection of installed Django 6.0.8 found no `kk/formats.py`; DATE_FORMAT and
  YEAR_MONTH_FORMAT fall back to global formats. Reuse translated month/weekday words and send a
  `year_first` flag for period labels. Yearless day headings need no change. Keep ru/en ordering.
- **Mobile facts**: Existing Competition label properties already resolve taxonomy and geography;
  the ancestry lookup is cached per object. Reuse them for visible city/sport and native details
  containing remaining facts and Info. Alternative: dropping columns loses FR-CAL-004 facts.
- **Map**: Keep home-area bounds and fallback center/zoom in settings; serialize using json_script.
  Tests override the fallback to a different part of the world. No location is inferred or invented.
- **Styling**: Preserve the PR's active-tab fills and contrasting frames in light/dark, expressly
  approved on 2026-10-24. Use skin variables, wrap navigation groups and preserve 44px tap areas.
- **CI failures**: The initial 44 browser failures were 42 navigation-width failures plus two
  asynchronous test races (album save and language preference). Fix the shared navigation and wait
  for the actual POST response in the two tests. A subsequent WebKit rounding regression in the
  expanded button hit area is fixed by zero insets on buttons already wider than 44px.
