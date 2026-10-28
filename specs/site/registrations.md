# Site Specification: Registration and the participant list

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21; a member's manager (issue #315) against branch `315-managing-registrations` on 2026-10-28
**Code**: `registrations/` (models, forms, registering, views), registration settings on `calendar_app.Competition`
**Tests**: `registrations/tests.py`, `tests/test_profile_registration_actions.py`,
`tests/test_bib_numbers.py`, `tests/test_additional_info_label.py`,
`tests/test_list_site_registration.py`, `calendar_app/tests.py` (registration open/limits),
`calendar_app/test_timezones.py`,
`tests/e2e/test_participant_list.py`, `test_relay_registration.py`, `test_profile_registrations.py`,
`test_registration_category_filter.py`, `tests/test_managing_registrations.py`,
`tests/test_managing_register_many.py`, `tests/e2e/test_managing.py`
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
2. **Given** self-only mode, **Then** a rider registers only themselves, needs a gender and a birth
   date in their profile, and their identity fields (names, birth, gender) are locked to the
   profile; **given** free mode, **Then** any person can
   be entered by name and birth year/date.
3. **Given** the same rider (self-only: the same account; free: the same name, case-insensitive, and
   birth year) is entered twice, **Then** the second entry is refused, unless the event allows
   several registrations (free mode only).
4. **Given** approval or payment is not required, **Then** a new entry is approved or paid at once;
   otherwise it waits.
5. **Given** a relay event, **Then** the form takes member names (one to the event's maximum, rows
   added and removed in place) instead of first and last name, and skips the duplicate check.
6. **Given** a member who manages other members' registrations ([accounts](accounts.md), issue
   #315) and an event that is not a relay, **Then** the page lists them first and then the members by
   last name, each with a checkbox; ticked, a person gets the event's form filled in from their own
   profile, and what the manager adds goes into the registration only. Whoever is entered already is
   left out, unless the event takes several entries from one person; in a self-only event a person
   without a gender or a birth date has no checkbox and a note to complete the profile (to ask the
   member to); in free mode "Another person" can be typed in as before. People are entered from the
   top, as many as can be: those entered lose their checkbox, the others keep it with the reason. A
   member's entry is theirs (`user`), submitted by the manager (`registered_by`), with the member's
   own profile data in a self-only event. In an invite-only event a manager who was let in may enter
   a member, who is then let in as though they had opened the invitation. With no members, or in a
   relay, the page is the page for one.

### Story 2 -- Change or withdraw an entry (P2)

1. **Given** the rider's own, not rejected entry, while registration is open by deadline, **Then**
   they may edit it (not its category or service flags; identity only in free mode) or cancel it;
   editing an approved entry returns it to waiting for approval. Whoever manages the rider's
   registrations does the same on the same terms; once that link ends, they no longer may.
2. **Given** the profile, **Then** open entries get a card with edit and cancel buttons, nearest race
   first; ridden or closed ones leave the section but stay in the table, which shows the race date,
   most recent first, and a badge only when an entry is rejected, waiting or unpaid.

### Story 3 -- Run the field (P1)

1. **Given** a manager of the event, **Then** they may approve, reject (with a note), mark paid,
   delete, add entries by hand (free mode only), edit any entry, and export a CSV.
2. **Given** the participant list, **Then** riders are grouped by category, each group numbered from
   its category's bib range (from 1 by default); uncategorised riders come last; the total and the
   limit stand by the title; a manager gets approve/reject and paid columns only when the event
   requires approval or payment, and a "Submitted by" column once any entry was submitted by someone
   other than its participant (a member's manager, or an organizer adding an entry by hand).

### Story 4 -- Read the field (P2)

1. **Given** anyone (a visitor included), **Then** the public list leaves out rejected entries, and
   -- where the event requires approval or payment -- unapproved or unpaid ones unless the organizer
   chose to show them; approval and payment status columns, and the additional-info column, appear
   to the public only when the organizer turned them on.
2. **Given** a phone, **Then** the list stacks into cards with a sticky category band under the
   navbar.

### Edge Cases

- A cancelled or deleted entry is erased, not soft-deleted; its event's categories are
  soft-deleted.
- Registration is open only for an approved event with registration enabled, before its deadline
  (date and time at the event's place), or without a deadline until the end of the event's last day
  there, and below the overall and per-category limits; a full field still lets its riders edit
  their entries.
- A manager keeps the entry buttons after the deadline.
- The event page shows the deadline in the event's zone with its UTC offset, and again in the
  reader's zone when the two offsets differ at that moment (issue #344).
- A pending event takes no entries: its registration form and its participant list are 404 to
  everyone but its managers, and registration stays closed even for them until it is approved.
- Relay member names are escaped on save and never rendered as HTML.
- The city autocomplete suggests only cities of entries that count in approved, visible events.
- A refused entry shows the page again whole: the category list keeps following the gender and the
  birth year, a relay team keeps the members typed in; the reason is in the page's language.
- A member's manager sees the member's entry in the participant list even where the event hides
  entries until approved or paid, as the member does.
- On the page for several, a box ticked for anyone other than the reader, their members, or another
  person where anyone may be entered is refused whole (403).

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

- **CompetitionRegistration**: event, user (optional in free mode), registered-by (who submitted it:
  the participant, their manager, or an organizer adding it by hand), names or relay
  member names/years/cities, birth date, gender, category, team, city, additional info, approved /
  paid / rejected flags and rejection note, registration time.
- **RegistrationCategory**: event, name, genders, birth-date range, laps, bib range, limit, order,
  soft delete.
- **Team**: shared names, restored rather than duplicated (case-insensitive).

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: Strava is the sport's de facto standard; a general tracker connector may come later, not as a fix). The additional-info field knows one service by name: a Strava link (`AdditionalInfoMode.STRAVA`).
- Payment is a yes/no flag; no currency or amount is modelled, so nothing local is assumed there.

## API gaps

- Entering a race, editing or cancelling one's own entry, and listing one's own entries -- and doing
  so for the members whose registrations one manages (issue #315).
- Running the field: approving, rejecting, marking paid, deleting, adding and editing entries, and
  exporting the list. `/participants/` serves the timing tools with the event's upload token, not a
  manager with their own token.
- Reading the public participant list.

## Open Questions

- None known.
