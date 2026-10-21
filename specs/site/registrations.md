# Site Specification: Registration and the participant list

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `registrations/` (models, forms, views), registration settings on `calendar_app.Competition`
**Tests**: `registrations/tests.py`, `tests/test_profile_registration_actions.py`,
`tests/test_bib_numbers.py`, `tests/test_additional_info_label.py`,
`tests/test_list_site_registration.py`, `calendar_app/tests.py` (registration open/limits),
`tests/e2e/test_participant_list.py`, `test_relay_registration.py`, `test_profile_registrations.py`,
`test_registration_category_filter.py`
**Related**: [events](events.md), [accounts](accounts.md), [API](api.md) (participants for the
timing apps)

## Overview

An organizer can take entries for an event on the site. Riders register themselves or -- in free
mode -- anybody; entries can wait for the organizer's approval and payment; the public participant
list groups riders by category with start numbers; the timing apps fetch the same list.

## User Scenarios

### Story 1 -- Enter a race (P1)

1. **Given** registration is open, **When** a participant opens the form, **Then** team, city and
   birth date come prefilled from their profile (birth date in ISO form whatever the language).
2. **Given** self-only mode, **Then** a rider registers only themselves, needs a complete profile,
   and their identity fields are locked to the profile; **given** free mode, **Then** any person can
   be entered by name and birth year/date.
3. **Given** the same rider (self-only: the same account; free: the same name, case-insensitive, and
   birth year) is entered twice, **Then** the second entry is refused, unless the event allows
   several registrations (free mode only).
4. **Given** approval or payment is not required, **Then** a new entry is approved or paid at once;
   otherwise it waits.
5. **Given** a relay event, **Then** the form takes member names (one to the event's maximum, rows
   added and removed in place) instead of first and last name, and skips the duplicate check.

### Story 2 -- Change or withdraw an entry (P2)

1. **Given** the rider's own, not rejected entry, while registration is open by deadline, **Then**
   they may edit it (not its category or service flags; identity only in free mode) or cancel it;
   editing an approved entry returns it to waiting for approval.
2. **Given** the profile, **Then** open entries get a card with edit and cancel buttons, nearest race
   first; ridden or closed ones leave the section but stay in the table, which shows the race date,
   most recent first, and a badge only when an entry is rejected, waiting or unpaid.

### Story 3 -- Run the field (P1)

1. **Given** a manager of the event, **Then** they may approve, reject (with a note), mark paid,
   delete, add entries by hand (free mode only), edit any entry, and export a CSV.
2. **Given** the participant list, **Then** riders are grouped by category, each group numbered from
   its category's bib range (from 1 by default); uncategorised riders come last; the total and the
   limit stand by the title; approve/reject and paid columns appear only when the event requires
   them.

### Story 4 -- Read the field (P2)

1. **Given** anyone (a visitor included), **Then** the public list shows the entries that count:
   not rejected, and approved/paid when the event requires it; the additional-info column only when
   the organizer chose to show it.
2. **Given** a phone, **Then** the list stacks into cards with a sticky category band under the
   navbar.

### Edge Cases

- Registration is open only for an approved event with registration enabled, before its deadline
  (date and time in Asia/Almaty), or without a deadline until the end of the event's last day, and
  below the overall and per-category limits; a full field still lets its riders edit their entries.
- A manager keeps the entry buttons after the deadline.
- A pending event's registration form and participant list are 404, except to its managers.
- Relay member names are escaped on save and never rendered as HTML.
- The city autocomplete suggests only cities of entries that count in approved, visible events.

## Functional Requirements

- **FR-REG-001**: Registration modes: self only (linked to the account) and free (any person); the
  mode locks once registration is first enabled.
- **FR-REG-002**: Birth is asked as a year or a full date, as the organizer chooses; categories
  match by gender and an inclusive birth-date range (an open bound matches everything).
- **FR-REG-003**: Additional info: off, free text, or a Strava link (prefilled from the profile,
  with a banner when the profile has none); optional or required; the organizer may name the field,
  and that wording reaches the form, the list column and the export (the built-in name follows the
  reader's language; the export header stays English).
- **FR-REG-004**: Start numbers are unique across the whole event: categories sharing a range take
  numbers in order, a lower range after a higher one keeps its own, a rider who does not count
  consumes no number, an empty category reserves none.
- **FR-REG-005**: An entry counts when it is not rejected, and approved and paid where the event
  requires it; counting entries fill the limits and get start numbers.
- **FR-REG-006**: Only participant and up register; guests are sent to confirm their address.

## Key Entities

- **CompetitionRegistration**: event, user (optional in free mode), registered-by, names or relay
  member names/years/cities, birth date, gender, category, team, city, additional info, approved /
  paid / rejected flags and rejection note, registration time.
- **RegistrationCategory**: event, name, genders, birth-date range, laps, bib range, limit, order,
  soft delete.
- **Team**: shared names, restored rather than duplicated (case-insensitive).

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- The additional-info field knows one service by name: a Strava link (`AdditionalInfoMode.STRAVA`).
- Deadlines are reckoned in `Asia/Almaty` whatever the event's place (`calendar_app/registration_deadline.py`).
- Payment is a yes/no flag; no currency or amount is modelled, so nothing local is assumed there.

## Open Questions

- None known.
