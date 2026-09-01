---
name: working-with-the-maintainer
description: How this project's maintainer works and what they expect back - language, tone, what needs asking first, and the standing agreements that hold across every task. Read at the start of a session.
---

# Working with the maintainer

One person runs this site, reviews everything and pays for it. These are their standing rules; they
were learned by being corrected, so treat them as settled rather than negotiable.

## Answering

- **Answer in Russian.** They write in Russian; replies, questions and reports go back in Russian.
  Code, comments, commit messages, documentation and interface source strings stay English.
- **Report plainly.** State the number, not how big a breakthrough it is. "3 of 4 events got a
  link, the fourth did not, and here is why" -- not "great news".
- **A question is a question.** When they ask "do you know how to fix X", answer with the approach
  and stop; they will say when to implement.
- **Do not invent.** "Nothing made up, facts only" is a rule they restate often. When a source
  contradicts itself, transcribe it and flag the contradiction rather than resolving it silently.
  If you had to interpret something, say so in the report -- explicitly, not buried.

## Ask before

- **Merging anything.** Never `gh pr merge`. Drive the pipeline green and stop.
- **Running an agent.** Every run spends money at the LLM provider.
- **Touching an approved event.** Its links, location or dates are the maintainer's to change.
- **A decision that changes the shape of the work**: whether a new field is one string or three
  per locale, what a clone must not copy. Offer two or three options with a recommendation and let
  them pick, before writing code.

## Batching

Merging takes the site down for a couple of minutes, so several unrelated tasks are often asked for
as **one pull request with a commit per task**. That is deliberate; do not split it into several
pull requests to be tidy.

## The default shape of a task

Unless they say otherwise: a branch of its own, one atomic commit per change, three review cycles
with each accepted finding as its own commit, then the pipeline driven green -- and no merge. Tests
come with the change, all three locales come with the change, and commit messages are one line with
no co-authorship line.

## Data work

Some tasks are edits to live content rather than code: fixing an announcement, merging duplicate
locations, moving articles between categories. Those are done straight against production (see
`production-access`), reported afterwards with what changed, and never mixed into a pull request.
