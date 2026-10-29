# Implementation Plan: An assistant that adds an event by asking about it

**Branch**: `353-assistant` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md) |
**Research**: [research.md](research.md)
**Status**: Built in pull request #405; the maintainer asked for the code to start once the spec's
questions were answered.

## Summary

A chat at the bottom right of the pages where an event is added and edited, for admins and the
owner. The server keeps the conversation with its event, asks the model and turns the model's answer
into checked values of the event's form, which the page fills in; the admin saves with the form's own
button. What to ask, and how an announcement reads, lives in skills: Markdown files the maintainer
edits, in a folder of the assistant's own.

## Technical Context

**Stack**: Django 6, django-ninja, gettext (ru / kk / en). No new dependency: the call to the model
is `urllib`, as the agents' is.
**Storage**: two tables in a new app, `assistant` (migration `0001_initial`).
**Model**: `deepseek-flash` through `agent.config.DEFAULT_LLM_MODEL`, which the `llm-model` CI job
already checks; thinking off, JSON output. One measured call on 2026-10-29 -- a full set of titles,
descriptions and link previews in three languages: 241 tokens in, 764 out, 4.4 seconds. Fast enough
to answer in one piece, without streaming.
**Testing**: unit tests per layer with the model's call replaced, never the real one; Playwright for
the chat on the add and edit pages, on a desktop and on a phone.

## Constitution Check

- **I (facts come from their source)**: the model fills only what the admin said. Links are kept
  only when they appear in the admin's messages. The place comes from the site's tree, a track the
  admin attached, or coordinates they typed. What nobody said stays empty and becomes a
  recommendation in the reply.
- **II (the maintainer's decisions)**: the chat draws in Bootstrap's and the skin's variables only;
  light and dark are not touched.
- **VI (anyone, anywhere)**: nothing about a sport, a place or a club is written in code.
  - The provider's address is a setting, and the model one constant shared with the agents.
  - What to ask and how to write lives in the skills, which are data.
  - Event types and disciplines come from the database.
- **VII (the API)**: every operation of the chat is under `/api/v1/assistant/`, for admins and the
  owner, by token or by the site's session.
- **X (every input is checked)**: the model's answer is input like any other.
  - Each value is checked against its field; descriptions pass through `sanitize_rich_html`
    before they reach the page.
  - The key never leaves the server: settings, then the request's header to the provider.
- **XI (the API keeps its promises)**: one router added, nothing changed.
- **XII (any screen)**: the chat is built phone first and folds away.

## Design

### The folder `assistant/` (a Django app)

- `models.py`:
  - `Conversation`: the event, one-to-one, empty until the event is saved, deleted with it; who
    started it; when.
  - `Message`: the conversation; `user` or `assistant`; who wrote it; the text shown in the chat;
    the form values a reply set; when.
- `skills/*.md`, in Russian, outside the ASCII hook as the agents' guidance files are:
  - `general.md`: the club's layout, no date in the text, the link preview line, three languages,
    the registration reminder (decision 16), only the event (decision 18);
  - `ride.md`: decision 11, then decision 13;
  - `race.md`: decision 14.
- `prompt.py`: the system prompt, then the conversation, then the turn.
  - The system prompt is the reply's contract (English, in code), then the skills, then the event
    types and the disciplines with their ids.
  - The turn carries today's date, the page's language, the form as it stands and what was
    attached.
  - What does not change comes first, so the provider's cache serves it at a fiftieth of the price.
- `llm.py`: one call.
  - Thinking off, `json_object`, `max_tokens` 6000, a 90-second timeout.
  - Every failure becomes `Unavailable` with a reason the admin can act on: no balance, key
    refused, provider busy.
- `fields.py`: the model's `set` becomes the form's values.
  - Texts are cut to their columns; descriptions are sanitized.
  - Dates are parsed; an end before the start is dropped.
  - Ids are kept only when they exist.
  - Links are kept only when they appear in the admin's messages, comparing without the scheme and
    `www.`.
  - The place goes through `places.py`.
  - What was dropped becomes a note the chat shows.
- `places.py`: the page's own list of places (`_get_locations_data`, so nothing the page cannot show
  is chosen) is turned into the agents' tree.
  - The city is found by `agent.locations.match_city`, the venue by `agent.venues.same_place` among
    the city's venues.
  - When no venue is named, the city's catch-all is used.
  - A venue that is not found becomes a new venue, with its three names and a point from the
    attached track or from coordinates the admin typed.
  - A city that is not found leaves the place empty, with a note.
- `conversations.py`:
  - start one, or find the event's;
  - one turn: the admin's message and the reply are stored together, only when the model answered,
    so a failed call can simply be sent again;
  - link one to the event the form saved.
- `api.py`, mounted at `/api/v1/assistant/`.
- `templatetags/assistant.py` and `templates/assistant/_chat.html`: the chat, offered to admins and
  the owner when the key is set.

### Outside the folder

- `submit.html`, `edit.html`: `{% assistant_chat %}`.
- `_location_cascade.html`: `window.eventLocation` with `select(pk)` (the cascade's own
  `selectExistingVenue`) and `propose(cityPk, names, lat, lng)`.
- `_filter_multiselect_js.html`: a `select(chains)` method beside `restoreChains`;
  `_disciplines_field.html`: `window.eventDisciplines.set(ids)`.
- `calendar_app/views.py`: the submit view links the conversation named in the form to the new
  event. The edit page needs nothing: its conversation is the event's.
- `api/router.py`: the router.
- `settings/base.py`: the app; `ASSISTANT_LLM_API_KEY`; `ASSISTANT_LLM_BASE_URL`
  (`https://api.deepseek.com` by default).
- `.pre-commit-config.yaml`: the skills outside the ASCII hook.
- `home/privacy_page.html`: the line of decision 19.

### API (`/api/v1/assistant/`)

| Operation | What it does |
| --- | --- |
| `POST /conversations {competition_id?}` | 201 with a new conversation, or 200 with the event's own |
| `GET /conversations/{id}` | the conversation and its messages |
| `POST /conversations/{id}/messages` | one turn; body `{text, form, today, language, attachments}`, answer `{reply, fields, notes}` |
| `PATCH /conversations/{id} {competition_id}` | links it to an event; 409 when either is taken |
| `POST /track-start` (a file) | the track's first point, or 422 |

- Auth: `member_auth`, then admins and the owner; anyone else gets 403.
- Without the key, a turn answers 503 with the reason.

### The page

- **The chat**:
  - a button with the words "Assistant", fixed at the bottom right;
  - on a desktop it opens a panel 380px wide; on a phone, the lower part of the screen, folding
    away to show the form;
  - the first question is the page's own text: one for a new event, another for an edit.
- **A turn**:
  - the form is read off the page and sent, the reply shown, and the values applied:
  - inputs by name; descriptions through `Quill.find`; the event types' options;
  - the disciplines and the place through the two hooks.
- **Attaching**:
  - a GPX or KML file goes into the form's route file, and its start is asked of `/track-start`;
  - a PDF goes into the regulations file;
  - the chat then sends the file's name as the admin's message, with the attachment described for
    the model.
- **Keeping the conversation**:
  - its id rides in a hidden input of the event's form, so saving links it;
  - a page that comes back with errors picks it up again.

## Risks, and what is done about them

- **An answer that invents.** Every value is checked as above, and the skills repeat the rule. The
  probe call shows why the skills must spell out the club's rules: unprompted, it repeated the date
  in the description and wrote a preview line three times too long.
- **The key spent on other work.** Decision 18 in the skills; a turn's text is capped at 10,000
  characters.
- **The site's four threads.** A turn holds one for its few seconds; the timeout frees a hung one.
- **The key leaking.** It lives in settings and in the request to the provider only. Tests check
  that neither a page nor an answer of the API carries it.
