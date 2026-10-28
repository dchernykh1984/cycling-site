# Feature Specification: Add an event to the reader's own calendar

**Feature Branch**: `398-add-to-calendar`
**Created**: 2026-10-28
**Status**: Implemented (pull request for issue #398)
**Input**: Issue #398 -- on an event's page, beside "Share", a button "Add to calendar" with a
calendar icon puts the event into the calendar the reader uses on this device: Apple's Calendar on
an iPhone, iPad or Mac, Google Calendar on Android, a calendar app or Google Calendar on a computer.
The maintainer asked for the pull request straight away, so this specification was written beside
the code and is reviewed with it.

## User Scenarios & Testing

### User Story 1 - Put an event into my calendar (Priority: P1)

1. **Given** a published event the reader can open, **Then** its page carries "Add to calendar"
   beside "Share", the same size and look: the icon alone on a phone, the icon and the word on a
   wider screen.
2. **When** the reader taps it, **Then** the browser gets the event's calendar file, which the
   device's calendar offers to add: Apple's Calendar on an iPhone, iPad or Mac, Outlook or the
   calendar app on a computer, a calendar app that takes files on Android.
3. **Given** the file, **Then** it holds the one event, all day from its first day to the day after
   its last, with its title, a summary and the link to its page in the page's language, its place,
   and the venue's own point when the venue has one.
4. Adding is a copy made once: an event moved on the site later does not move in the reader's
   calendar. Following changes is the calendar subscription (issue #333).

### User Story 2 - A program reads one event's calendar file (Priority: P2)

1. **Given** an API client, **Then** `GET /api/v1/competitions/{id}/ics` returns the same file, in
   the language it asks for (`lang`, the site's default otherwise), under the API's own rule of who
   sees which event.

### Edge Cases

- An event awaiting review or rejected: no button. Its file answers whoever may open its page (its
  author, its moderators) and 404 to everyone else -- the page's own rule.
- A hidden event: its managers only. An invite-only one: its managers and the people let in, as on
  its page; the API serves it to no invitee, as for its other reads. A deleted one: nobody.
- Events carry days and no start time (a time stays in the description, the maintainer's choice),
  so the calendar entry lasts whole days and needs no time zone.
- A venue with no point of its own, or a city's catch-all venue: the place by name, no point.
- Google Calendar's own app on Android does not open a calendar file, as far as is known: its
  reader adds the event another way. The file alone, with no link to a calendar service, is the
  maintainer's choice (2026-10-28).

## Requirements

- **FR-001**: The file is built by the code that builds the calendar subscription
  (`calendar_app/feeds.py`), so the two never disagree about an event.
- **FR-002**: The file and the event's page answer the same people (`calendar_app/visibility.py`).
- **FR-003**: The button answers a tap across 44 px on a phone and is named in words in every
  language.

## Open Questions

- Not tried on real devices: Safari on an iPhone and a Mac opening the file, Android's calendar
  apps.
