# Site Specification: The event assistant

**Status**: Baseline -- describes the site as it works today
**Verified against**: branch `353-assistant` on 2026-10-29
**Code**:
- `assistant/`: `models.py`, `llm.py`, `prompt.py`, `skills/*.md`, `fields.py`, `places.py`,
  `conversations.py`, `api.py`, `assistant/templatetags/assistant.py`,
  `assistant/templates/assistant/_chat.html`;
- the event form's hooks in `calendar_app/templates/calendar_app/`:
  - `_location_cascade.html` (`window.eventLocation`);
  - `_disciplines_field.html` (`window.eventDisciplines`);
  - `_filter_multiselect_js.html` (`select`);
- the link made on saving, in `calendar_app/views.py` (`SubmitCompetitionView`).

**Tests**: `assistant/tests/` (models, llm, prompt, places, fields, conversations, api, chat),
`tests/e2e/test_event_assistant.py`
**Related**: [events](events.md), [API](api.md), [locations](locations.md),
[events agents](events-agents.md); `specs/353-event-assistant/` (the decisions, the research, the plan)

## Overview

Admins and the owner add and edit events by talking. A chat on the event's page asks what a rider
needs to know and fills the form in three languages; the admin saves it with the form's own button.

What to ask, and how an announcement reads, are skills. These are Markdown files in Russian under
`assistant/skills/`, which the maintainer edits as experience shows what announcements lack.

## User Scenarios

### Story 1 -- An admin adds an event by talking (P1)

1. **Given** an admin or the owner on `/<lang>/calendar/submit/`, and the site has the model's key,
   **Then** a button "Assistant" at the bottom right opens the chat. Its first question is the
   page's own text, so the model is not asked anything until the admin writes.
2. **Given** a message, **Then** the site sends the model the skills, the event types and the
   disciplines, the conversation, the form as it stands and the admin's date.
   - The reply comes in the page's language.
   - The form fills in: titles, descriptions and link previews in ru / kk / en, the dates, the
     types, the disciplines, the links and the place.
3. **Given** the form saved, **Then** the conversation belongs to the new event.
4. **Given** a form that came back with errors, **Then** the chat comes back with its conversation.

### Story 2 -- An admin edits an event by talking (P1)

1. **Given** the event's edit page, **Then** the chat shows the event's conversation and goes on
   with it.
2. The model is told it edits, and changes only what it is asked to.

### Story 3 -- Files (P2)

1. **Given** a GPX or KML file attached in the chat, **Then** it goes into the form's route file,
   and its first point becomes the point of a new venue.
2. **Given** a PDF, **Then** it goes into the regulations file, and is neither read nor checked.

### Edge Cases

- **A link the admin did not write** is not put in the form, and the chat says it was left out. A
  link the form already holds -- an edited event's own, or one in its descriptions -- is kept.
- **The place**:
  - a venue of the site's, when the name matches it (the import agents' matching);
  - the city's catch-all, when no spot is named;
  - otherwise a new venue with its three names;
  - a city the site does not have leaves the place empty, with a note.

  Coordinates come only from a track or from numbers the admin typed.
- **When the model fails** -- no money on the account, the key refused, no answer -- nothing is kept
  and the chat says what to do. The admin's text stays, to be sent again.
- **Anything but the event**, such as writing code, is turned down, as the skills instruct.
- **Wagtail's own button for editors** takes the bottom-right corner. The chat's button sits to its
  left, and the open chat hides it.

## Functional Requirements

- **FR-AST-001**: Only admins and the owner are offered the chat and may use `/api/v1/assistant/`.
  Without `ASSISTANT_LLM_API_KEY` the chat is not offered, and a turn answers 503.
- **FR-AST-002**: The key is used only in the server's request to the provider. No page and no
  answer of the API carries it.
- **FR-AST-003**: The model's answer is checked before it reaches the page:
  - texts are cut to their columns, and descriptions are sanitised;
  - dates are parsed, and only ids that exist are kept;
  - links must come from the admin's messages or the form as it stands, and places from the
    site's tree.
- **FR-AST-004**: A turn -- the admin's message and the reply together -- is stored only when the
  model answered.
- **FR-AST-005**: The model is the agents' constant (`DEFAULT_LLM_MODEL`), with thinking off and JSON
  output. The provider's address is `ASSISTANT_LLM_BASE_URL`.

## Key Entities

- **`Conversation`**: one per event (empty until the event is saved); who started it.
- **`Message`**:
  - user or assistant, and who wrote it;
  - the text;
  - for a reply, the form values it set, in the model's own words;
  - for the admin's message, the files it attached.

## Local assumptions

None in code. The skills are in Russian, the maintainer's language, and they are data.

## API gaps

None: the chat is built on `/api/v1/assistant/`.

## Open Questions

None.
