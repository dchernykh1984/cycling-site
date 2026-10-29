# The event assistant

A chat on the pages where an event is added and edited, for admins and the owner (issue #353). It
asks what a rider needs to know, fills the event's form in three languages, and the form's own
button saves it. The conversation is kept with the event, so the edit page goes on with it.

How it behaves is in `specs/site/assistant.md`; why, in `specs/353-event-assistant/`.

## The skills

`skills/*.md` are the assistant's instructions: what to ask, and how an announcement is written.
They are in Russian, outside the ASCII hook, and every file in the folder goes into every request in
the order of the names. Change them as experience shows what announcements lack:

- `general.md`: how to talk, how an announcement reads, the link preview, registration, the ending;
- `ride.md`: what to ask about a ride;
- `race.md`: what to ask about a race.

What was learned writing them, on the model itself:

- **An example becomes the text.** The model copies an example's words into the announcement as
  if they were said. Give the form of a thing with placeholders (`<what> <where to>`), not a
  sample.
- **Naming what not to ask makes it ask.** "Do not ask who leads the group" had it ask exactly
  that. Leave out what should not be asked.
- **It repeats what it filled in.** "Say in one sentence what you filled in, without listing it"
  stopped it.

## What the model is told, and what is checked

`prompt.py` builds each request:

- **the system part**: the reply's contract in English, the skills, the event types and the
  disciplines with their ids;
- **the conversation so far**;
- **the turn**: the admin's date and the page's language, the form as it stands, the files, and
  the message.

The system part stays the same between turns, so the provider's cache serves it cheaply.

`fields.py` checks the answer before the page sees it:

- **links** must come from the admin's messages or from the form as it stands;
- **a place** must be one of the site's, found by `places.py` with the import agents' matching;
- **coordinates** come only from a track or from numbers the admin typed.

## The model and the key

- **The model** is `agent.config.DEFAULT_LLM_MODEL`, which CI checks the provider still serves.
  It is called with thinking off and JSON output.
- **The key** is `ASSISTANT_LLM_API_KEY` in the site's environment, and never leaves the server.
  Without it the chat is not offered.
- **The address**: `ASSISTANT_LLM_BASE_URL` points at another OpenAI-compatible provider.
- **Tests** replace `assistant.llm.complete` and never reach the provider.
