# Data and state

No persistent entity, database field or migration is added.

- **Competition**: Existing localized title, event types, disciplines, geography, dates and links.
  Existing visibility, soft deletion and registration availability remain authoritative.
- **Period selection**: Inclusive ISO date boundaries. A current-month selection is floating;
  explicit noncurrent ranges are fixed. Named kinds drive arrow steps.
- **Browser session**: Existing `cal_date_from`, `cal_date_to`, `periodKind` and filter state;
  `cal_layout` remembers grid/list. Storage may be unavailable, so in-memory selection remains usable.
- **Configuration**: `MAP_HOME_AREAS` contains named bounds; `MAP_DEFAULT_VIEW` contains center/zoom.

Order of period resolution: explicit date query, explicit floating-month marker, stored range,
current month. Layout resolution is independent: explicit period action, stored layout, viewport
default. An explicit short range always uses a list; Month always chooses the grid.
