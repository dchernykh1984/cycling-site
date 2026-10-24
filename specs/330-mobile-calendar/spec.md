# Feature Specification: A calendar that reads on a phone

**Feature Branch**: `330-mobile-calendar`
**Created**: 2026-10-24
**Status**: Review remediation in PR #343
**Input**: Issue #330, PR #343 and the maintainer's review instructions of 2026-10-24.

The original implementation predates the project's Spec Kit constitution. This specification
records the current reviewed scope; it does not claim a specification preceded that implementation.
The maintainer delegated the phone's default layout and explicitly approved the PR's active-tab
fills and period-control frames in light and dark. The selected phone default is a list of days,
with Month opening the grid. Existing data and permission rules stay as they are.

## User Scenarios & Testing

### User Story 1 - Find an event on a phone (Priority: P1)

A reader opens the calendar and reads event names without squeezing them into seven columns.

**Why this priority**: This is the problem stated in issue #330.
**Independent Test**: Open a fresh calendar on a phone, read its days, then choose Month.

**Acceptance Scenarios**:

1. **Given** a fresh visit below 992px, **When** the calendar opens, **Then** the current month's
   remaining days are listed; at 992px and above the month opens as a grid.
2. **Given** the phone list, **When** Month is chosen, **Then** the month grid opens; a chosen
   layout survives another visit in the same browser session and is not changed by resizing.
3. **Given** five events on one day in the grid, **Then** three show and +2 opens all five.
4. **Given** a multi-day event in a calendar list, **Then** it appears once with its end day.

### User Story 2 - Keep and share a selection (Priority: P1)

A reader chooses a period and filters once, moves between views, and shares what is on screen.

**Why this priority**: A link that silently changes its range is unreliable.
**Independent Test**: Choose a weekend, follow the list and map links, reopen the calendar, and
open a shared current-month link in a session that previously selected another period.

**Acceptance Scenarios**:

1. **Given** any view, **Then** Today tomorrow, Weekend, Week and Month choose a named range;
   the month and year labels open pickers; arrows move by the selected period and Today returns
   to the current period of that kind.
2. **Given** a phone, **Then** filters are initially folded behind a named icon with their count;
   active filters have removable chips and an opened panel remains open during the visit.
3. **Given** an explicit range in a link, **Then** it wins over stored choices; a fresh current-month
   share link explicitly names that period without pinning the day the link was copied.
4. **Given** a range selected on the calendar, **Then** a later visit through the calendar menu
   restores it unless the incoming link explicitly chooses another period.

### User Story 3 - Tell events apart (Priority: P1)

A reader can distinguish similarly named events by sport and place, and find their information
and registration links on a phone as well as on a desktop.

**Why this priority**: A shorter layout must not remove the facts promised by FR-CAL-004.
**Independent Test**: Open an event with types, disciplines, full geography and links on a phone.

**Acceptance Scenarios**:

1. **Given** the List tab below 992px, **Then** events are grouped by their start day; a wide
   screen retains the table and the same pagination.
2. **Given** a mobile row, **Then** its city and sport are visible and its full type, direction,
   discipline, country, region and venue facts remain available in that row's details.
3. **Given** an announcement and available registration, **Then** both links can be reached;
   registration on this site takes precedence over an external registration link.

### User Story 4 - Use the same calendar anywhere (Priority: P2)

A reader uses their language, skin and places without changing the application's code.

**Why this priority**: These are the constitution's language, geography and access requirements.
**Independent Test**: Browse ru, kk and en in each skin, set a different map fallback, and use the
period picker with a keyboard.

**Acceptance Scenarios**:

1. **Given** ru, kk or en, **Then** labels are translated; Kazakh period labels put the year before
   the month or day, including both boundaries when a range crosses years.
2. **Given** selected mapped places in one configured home area, **Then** the map starts there;
   otherwise it fits matching markers or uses its configured fallback center and zoom.
3. **Given** a keyboard user, **Then** picker focus returns to its trigger after Escape or a choice;
   phone controls answer a 44px tap without overlapping their neighbours.
4. **Given** any supported skin and language, **Then** the page fits the tested widths, controls
   retain accessible names and the approved selection styling remains recognizable.

### Edge Cases

- Sunday means the remaining Sunday of this weekend; weekend arrows still move by whole weekends.
- The plain list and map stop at the current month's end; a faceted list keeps its open future
  range unless dates are supplied explicitly. Date-range filtering of already-running events is
  tracked separately in issue #352 and is not changed here.
- Empty results preserve the selected controls. Missing event metadata is not invented.
- A private, hidden or unapproved event remains subject to the existing visibility rules.
- Blocking browser storage does not prevent reading or changing a period.

## Requirements

### Functional Requirements

- **FR-001**: The fresh phone calendar MUST list days; Month MUST open the grid. A chosen layout
  MUST be retained for the visit and MUST NOT switch on resize.
- **FR-002**: All views MUST share named period navigation and carry the displayed range and filters.
- **FR-003**: Explicit link selections MUST win over session state; reopening the calendar MUST
  restore the session's period when the link makes no explicit selection.
- **FR-004**: Phone filters MUST fold, count active kinds, show removable chips and retain panel state.
- **FR-005**: A grid day MUST show at most three events before its +N control; list ranges MUST show
  a multi-day event once with its end day.
- **FR-006**: The List tab MUST preserve FR-CAL-004's facts and links on every screen; mobile rows
  MUST show city and sport without opening a separate event page.
- **FR-007**: The initial plain list and map MUST use the remaining current month; a faceted list
  MUST retain the existing open future range, and supplied dates MUST win.
- **FR-008**: Home areas and the empty-map fallback MUST come from named configuration values.
- **FR-009**: All new words MUST be available in ru, kk and en; the Kazakh period MUST put years first.
- **FR-010**: Controls MUST remain named, keyboard reachable and usable at the tested widths and
  tap sizes in every skin; existing documented skin debt MUST NOT be expanded to hide new defects.
- **FR-011**: Event visibility, registration rules, pagination and API v1 contracts MUST be preserved.
- **FR-012**: Specifications, mirrored guidance and tests MUST describe the final implementation;
  source changes MUST be ASCII and UTF-8.

### Key Entities

- **Event**: existing translated event facts, dates, visibility and links; no new persistent fields.
- **Selection**: a period, layout and filters retained during a browser visit; links carry explicit choices.
- **Map configuration**: named home-area bounds and fallback center/zoom, independent of event data.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a fresh phone visit, a reader can read a day's event names without seven-column clipping.
- **SC-002**: Every explicit shared range opens on its named days regardless of an earlier selection.
- **SC-003**: Every listed event retains its sport, place, information and registration facts on a phone.
- **SC-004**: All supported language/skin combinations pass the project's phone and desktop checks;
  test widths are 320, 360, 768, 1024 and 1280px.
- **SC-005**: No production event or user data is rewritten, and existing API clients retain their contracts.

## Assumptions

- A phone is a viewport below the existing 992px layout breakpoint; the layout is selected only
  when the calendar is opened, not on resize.
- Existing three locales and skin variables are reused; no new dependencies, models or migrations.
- The end-of-month default and open faceted-list range retain the PR's existing scope; #352 remains separate.
- The maintainer's 2026-10-24 delegation and light/dark approval settle the current UI choices.
