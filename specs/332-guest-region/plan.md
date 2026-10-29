# Implementation Plan: A guest's calendar opens on their region

**Branch**: `332-guest-region` | **Spec**: [spec.md](spec.md)

## Approach

- `calendar_app/guest_region.py`: the point from the `CF-IPLatitude` / `CF-IPLongitude` headers;
  the approved cities in a box around it, measured with the agent's haversine
  (`agent.venues.distance_metres`, one home for the formula); the nearest within the radius gives its
  parent region; `listed_for` decides whether the guest would see anything still to come there.
- `DefaultFilterRedirectMixin` (calendar, list, map): after a member's saved preferences, a guest's
  region, as a redirect to `?location=<region>` that also sets the visit cookie.
- Settings: `GUEST_REGION_RADIUS_KM`, `BOT_USER_AGENT_MARKERS`.
- The privacy policy gains a paragraph, translated.

## Constitution Check

- I (facts from their source): the region comes from the provider's point and the site's own places.
- VI (no local hardcoding): no country, city or radius in the code; the radius and the markers are
  settings.
- X (inputs checked, privacy): the headers are parsed and range-checked; nothing is stored; the
  policy says so.
- III (tests): unit tests for every branch, an end-to-end test of the visit.
