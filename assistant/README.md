# The event assistant

A chat on the pages where an event or a news item is added and edited, for admins and the owner
(issue #353). The form's own button saves either, and the conversation is kept with its event or
news item, so the edit page goes on with it.

- **On an event's page** it asks what a rider needs to know and fills the form in three languages.
- **On a news item's page** it translates the item, puts its formatting right and changes it as
  asked.

How it behaves is in `specs/site/assistant.md`; why, in `specs/353-event-assistant/`.

## The skills

`skills/event/` holds the event assistant's instructions: what to ask, and how an announcement is
written. They are in Russian, outside the ASCII hook, and every file goes into every request about
an event: the shared ones first, then each kind of event's folder. Each kind has a folder of its
own, so that changing one kind's file leaves the others as they were. Change them as experience
shows what announcements lack:

- `general.md`: how to talk, the type, direction and discipline, how an announcement reads, the
  link preview, registration, the ending;
- `ride/`: what to ask about a ride, and how its description reads;
- `race/`: the same for a race;
- `multiday/`: a multi-day event and its stages -- whether the whole is added or one stage,
  whether the stages get pages of their own, and how the pages link to one another.

`skills/news/*.md` are the news assistant's: how to translate, format and change a news item. Both
kinds share the code and the key; only what the model is told differs.

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

- **links**, in the link fields and inside the texts, must come from the admin's messages or from
  the form as it stands;
- **pictures** in a description or a news text travel as marks (`images.py`) and come back in place;
- **a place** must be one of the site's, found by `places.py` with the import agents' matching;
- **coordinates** come only from a track or from numbers the admin typed.

## The model and the key

- **The model** is `agent.config.DEFAULT_LLM_MODEL`, which CI checks the provider still serves.
  It is called with thinking off and JSON output.
- **The key** is `ASSISTANT_LLM_API_KEY` in the site's environment, and never leaves the server.
  Without it the chat is not offered.
- **The address**: `ASSISTANT_LLM_BASE_URL` points at another OpenAI-compatible provider.
- **Tests** replace `assistant.llm.complete` and never reach the provider.
