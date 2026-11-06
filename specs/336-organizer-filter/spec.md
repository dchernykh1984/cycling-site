# Feature Specification: The calendar's organizer filter

**Issue**: #336
**Status**: Built
**Decided with the maintainer**: 2026-11-06, in conversation; recorded here

## Scope

The issue asks for an organizer field on events, shown and filtered by, with a club's events picked
out. The maintainer narrowed it: no teams or clubs of organizers, only the member who posted an
event. It comes with the organizers' ratings (#436): an organizer's name on the Ratings tab opens
their events.

## Decisions

1. **Who an organizer is.** The member who posted the event (`Competition.submitted_by`), the same
   person the organizers' ratings rate. The account the site's agents post through is not offered:
   what it posts was found, not organized.
2. **Who is offered.** Everybody with a public event, named last name first, in one searchable
   list of boxes like the places' filter, on the list, the grid and the map.
3. **What a list about organizers shows.** All their events, past and to come -- from the first
   day of the earliest to the last of the latest -- unless a period is asked for. Choosing or
   dropping an organizer on the list lets go of the days the list showed. The grid keeps its month
   and the map its days, as with any filter.
4. **From the Ratings tab.** An organizer's name opens the calendar's list filtered to them.
5. **The API** takes `organizer_ids` on the event list and lists the choices
   (`GET /api/v1/competitions/organizers`).

## Not built

- Teams or clubs of organizers, and picking a club's events out in the calendar.
- Keeping an organizer in a member's saved filter preferences.
