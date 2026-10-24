# Calendar UI contract

## Addresses and browser state

- `/ru/calendar/`, `/kk/calendar/`, `/en/calendar/`: initial layout by viewport or saved layout.
- `date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`: explicit inclusive range; wins over session dates.
- `period=month`: explicit current month, moving with the day it is opened; wins over session dates.
- Existing filter parameters and List/Map paths remain compatible. Favorites are not shared.
- Shared current-month links include `period=month`; other ranges include their dates.
- Calendar changes update switcher links and session state without a full-page navigation.
- Reopening a bare calendar URL restores the selected period; resizing never changes layout.

## Data and operations

No new member operation or v1 endpoint is introduced. Existing event list/detail data is already
available through `/api/v1/`; existing calendar JSON and location endpoints keep their contracts.
Native details in mobile List rows expose existing event facts, not new stored data.

## Interaction

Month/year picker buttons retain their accessible names and return focus after selection or Escape.
Phone List rows retain information and registration links, with on-site registration taking priority.
A grid shows three events and +N; a list shows a multi-day event once with its end day.
