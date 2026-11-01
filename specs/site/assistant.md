# Site Specification: The event assistant

**Status**: Baseline -- describes the site as it works today
**Verified against**: branch `353-assistant` on 2026-10-29; opened to organizers against branch
`assistant-for-organizers` on 2026-10-31
**Code**:
- `assistant/`: `models.py`, `llm.py`, `prompt.py`, `skills/event/*.md`, `skills/news/*.md`,
  `images.py`, `fields.py`, `places.py`, `conversations.py`, `api.py`,
  `assistant/templatetags/assistant.py`, `assistant/templates/assistant/_chat.html`;
- the event form's hooks in `calendar_app/templates/calendar_app/`:
  - `_location_cascade.html` (`window.eventLocation`);
  - `_disciplines_field.html` (`window.eventDisciplines`);
  - `_filter_multiselect_js.html` (`select`);
- the link made on saving, in `calendar_app/views.py` (`SubmitCompetitionView`) and `news/views.py`
  (`NewsArticleCreateView`); the chat on `news/templates/news/article_form.html`.

**Tests**: `assistant/tests/` (models, llm, prompt, images, places, fields, conversations, api,
access, chat), `tests/e2e/test_event_assistant.py`
**Related**: [events](events.md), [API](api.md), [locations](locations.md),
[events agents](events-agents.md); `specs/353-event-assistant/` (the decisions, the research, the plan)

## Overview

Organizers and up write events by talking, and admins and up news as well.

- **On an event's page** the chat asks what a rider needs to know and fills the form in three
  languages.
- **On a news item's page** it translates the item, puts its formatting right and changes its text as
  asked.

Whoever writes saves either with the form's own button.

What the assistant is told is in skills: Markdown files in Russian under `assistant/skills/event/`
and `assistant/skills/news/`, which the maintainer edits as experience shows what is missing. Each
kind of event has a folder of its own under `event/`, beside the shared `general.md`, so that a
change to one kind leaves the others as they were. One key, `ASSISTANT_LLM_API_KEY`, serves both.

## User Scenarios

### Story 1 -- An organizer adds an event by talking (P1)

1. **Given** an organizer or anyone above on `/<lang>/calendar/submit/`, and the site has the
   model's key, **Then** a button "Assistant" at the bottom right opens the chat. Its first question
   is the page's own text, so the model is not asked anything until they write.
2. **Given** a message, **Then** the site sends the model the skills, the event types and the
   disciplines, the conversation, the form as it stands and the user's date.
   - The reply comes in the page's language.
   - The form fills in: titles, descriptions and link previews in ru / kk / en, the dates, the
     types, the disciplines, the links and the place.
   - What the model asks follows the kind of event, each kind's skill in its own folder: a ride; a
     race (format, schedule, entrants, fee and limit, then prizes, rules, weather and a contact);
     a multi-day event, where it asks whether the whole or one stage is added, whether the stages
     get pages of their own, and, for a stage, which stages it links to and where the whole is
     announced. A link to one of the site's own pages may stand in each language's text with that
     language's prefix.
   - While the form has no event type, direction or discipline, each turn tells the model so: the
     calendar's filters select by them, and the model asks for them rather than guessing them from
     "a ride".
3. **Given** the form saved, **Then** the conversation belongs to the new event.
4. **Given** a form that came back with errors, **Then** the chat comes back with its conversation.

### Story 2 -- An organizer edits their event by talking (P1)

1. **Given** the edit page of an event they manage (their own; any, for an admin), **Then** the chat
   shows the event's conversation and goes on with it: whoever manages the event sees what was said
   about it, an admin's messages included. Its author below an organizer edits it without the chat.
2. The model is told it edits, and changes only what it is asked to.

### Story 3 -- An admin writes a news item with the chat (P1)

1. **Given** an admin or the owner on the news item's add or edit page, **Then** the chat's first
   question is the page's own text.
2. **Given** a request, **Then** the reply changes what was asked, in the languages asked:
   - translating the headline, the short description or the text;
   - putting the text's formatting right;
   - rewriting it as the admin says.
3. **Given** the item saved, **Then** the conversation belongs to it, and its edit page goes on with it.

### Story 4 -- Files (P2)

1. **Given** a GPX or KML file attached in the chat, **Then** it goes into the form's route file,
   and its first point becomes the point of a new venue.
2. **Given** a PDF, **Then** it goes into the regulations file, and is neither read nor checked.
3. **Given** an event with no route file, **Then** the chat says plainly, even when the event has a
   link to its track, that the track is drawn on the event's map only from a GPX file and asks for
   one; a link alone draws nothing (maintainer, 2026-11-01).

### Edge Cases

- **A link the user did not write** is not put in the form, and the chat says it was left out. This
  holds for the link fields and for a link inside a description or a news text.
  - A link the form already holds -- an edited event's own, or one in its texts -- is kept.
- **Pictures in a description or a news text** go to the model as short marks and come back in their
  places; a picture the model adds goes.
- **The place**:
  - a venue of the site's, when the name matches it (the import agents' matching);
  - the city's catch-all, when no spot is named;
  - otherwise a new venue with its three names;
  - a city the site does not have leaves the place empty, with a note.

  Coordinates come only from a track or from numbers the user typed.
- **When the model fails** -- no money on the account, the key refused, no answer -- nothing is kept
  and the chat says what to do. The user's text stays, to be sent again.
- **What is not theirs**: an organizer reaches the conversations they started and those of their own
  events. Another's conversation or event is a 404 in the API, and a refused form never brings back
  a conversation that is not theirs.
- **Anything but the event**, such as writing code, is turned down, as the skills instruct.
- **Wagtail's own button for editors** takes the bottom-right corner. The chat's button sits to its
  left, and the open chat hides it.

## Functional Requirements

- **FR-AST-001**: Organizers and up, and a superuser, are offered the event's chat and may use
  `/api/v1/assistant/`; the news chat is for admins and up (decision 27).
  - An organizer reaches the conversations they started and those of the events they manage:
    anything else is a 404, and starting a news item's conversation a 403.
  - Anyone below an organizer gets 401 or 403 on every operation, by token and by session, and the
    model is not asked.
  - The site's session needs the page's CSRF token.
  - Without `ASSISTANT_LLM_API_KEY` the chat is not offered, and a turn answers 503.
- **FR-AST-002**: The key is used only in the server's request to the provider. No page and no
  answer of the API carries it.
- **FR-AST-003**: The model's answer is checked before it reaches the page:
  - texts are cut to their columns, and descriptions are sanitised;
  - dates are parsed, and only ids that exist are kept;
  - links must come from the user's messages or the form as it stands, and places from the
    site's tree.
- **FR-AST-004**: A turn -- the user's message and the reply together -- is stored only when the
  model answered.
- **FR-AST-005**: The model is the agents' constant (`DEFAULT_LLM_MODEL`), with thinking off and JSON
  output. The provider's address is `ASSISTANT_LLM_BASE_URL`.

## Key Entities

- **`Conversation`**: an event's or a news item's (`kind`), one per subject, empty until the subject is
  saved -- never both; who started it.
- **`Message`**:
  - user or assistant, and who wrote it;
  - the text;
  - for a reply, the form values it set, in the model's own words;
  - for the user's message, the files it attached.

## Local assumptions

None in code. The skills are in Russian, the maintainer's language, and they are data.

## API gaps

None: the chat is built on `/api/v1/assistant/`.

## Open Questions

None.
