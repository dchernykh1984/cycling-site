# Feature Specification: An assistant that adds an event by asking about it

**Feature Branch**: `353-assistant`
**Created**: 2026-10-29
**Status**: Agreed with the maintainer on 2026-10-29; built in pull request #405; opened to
organizers on 2026-10-31 (decision 27)
**Issue**: [#353](https://github.com/dchernykh1984/cycling-site/issues/353); it also settles
[#361](https://github.com/dchernykh1984/cycling-site/issues/361) (machine translation of the locales)
for events
**Input**: An admin tells a chat what event they want to add; the chat asks what a rider needs to
know, fills the event's form on the page in three languages, and leaves the publishing to the admin.

## Decisions

Taken in conversation with the maintainer on 2026-10-29, in the order they came.

1. **Admins and the owner only, for now.** Organizers keep adding events by hand. Once it is known
   how fast the assistant spends its tokens, it may be opened to organizers -- and later, perhaps,
   to others for a fee.
2. **A chat at the bottom right of the page where an event is added**, not a page of its own. It
   opens with "What event would you like to add?", which is the page's own text: no call to the
   model happens until the admin writes something.
3. **It fills the form on the page.** As the admin writes, the site asks the model and fills the
   event's fields in front of them -- titles, descriptions and the link preview in the three
   languages, types, disciplines, the place, dates and links. Nothing is saved until the admin
   presses the form's own button; the assistant writes nothing to the event itself.
4. **The cheapest model of DeepSeek, called by the site's server only.** The key lives in the
   site's environment; the browser talks to the site, never to the model, and the key never appears
   in a page, a request from the browser or a response. The model is named in code and the pipeline
   checks it is still served, as for the import agents (pull request #403).
5. **An ending in words.** When everything needed is known, the chat says it has learned and filled
   it all, that the admin may ask for changes in their own words or edit the form by hand, and what
   would still help -- a GPX file to attach when there is no link to the track, for instance. The
   track is asked for in the chat first, as a link.
6. **No translator for events.** The model writes every text in Russian, Kazakh and English, so
   #361 is closed once the assistant is built; until then it stays open.
7. **The "skill" is instructions for any assistant** -- DeepSeek today -- on how to fill an event.
   This is what the maintainer cares most about: most rides are added without what a rider needs
   to know, which is then asked again in chat floods. The assistant asks for all of it, and asks
   differently for a race and for a ride.
8. **No limits for admins.** There are few of them, and a spend is someone's. (Counting each
   admin's tokens on the site was dropped later the same day: decision 17.)
9. **Nothing invented** (the site's standing rule). Links come only from the admin's messages; a
   place comes from the tree, a point on the map, a track's first point or the geocoder, never from
   the model; what nobody said stays empty and becomes a recommendation at the end.
10. **A new venue has its name in each language** (pull request #403), so the assistant can fill
    all three.
11. **What an announcement says** -- the maintainer's guidance while event 807 was put right by hand,
    and so what the assistant asks for a ride:
    - the start: the exact place and the time. Not the date: the event's fields carry it, and the
      description does not repeat it;
    - the route: where to, by name; groups that part on the way (an MTB group going on alone)
      said plainly; the track as the page offers it -- a Strava link and a GPX file to download are
      two things, named apart;
    - the finish: where (often at the start);
    - what happens after: the club's custom, such as tea and coffee at the start for everyone who
      finished, whatever their strength or speed;
    - registration on the site, when it is on: optional, what it is for (how many come, waiting for
      latecomers), and a request to delete one's registration on a change of mind;
    - the line a chat shows under the link (the preview text): very short -- what and where to
      ("UBT coffee ride to Yunnatskoye Lake"), the date, the time, the start;
    - the club's layout: an opening line, a list with bold labels (start, route, finish), then
      paragraphs; every text in the three languages.
12. **A folder of its own.** The assistant lives apart from the rest of the site, in a folder of its
    own in the project, and so do its skills -- the instructions on adding an event, which grow as
    experience shows what announcements lack and what can be had without asking (2026-10-29).

The maintainer's answers to the open questions, later on 2026-10-29:

13. **What it asks about a ride**, besides decision 11: the pace, and how the group waits for those
    behind, when it does. Not the distance, the climbing or anything else a track shows: it asks for
    the track's link, or for a GPX file to attach, or reminds the admin to attach one afterwards.
    Not who leads, nor where a cancellation is announced -- not for now.
14. **What it asks about a race**: the start's point on the map; the track, which shows the start
    and the finish; the categories -- or simply the regulations as a PDF. The PDF is the organizer's
    business: the assistant asks for it and attaches it, and neither reads nor checks it.
15. **Editing an event through the chat, from the first version.** The conversation is kept on the
    server with the event, and the event's edit page continues it with the whole context: asking to
    add, remove or change anything.
16. **Registration is switched on by hand.** The assistant reminds the admin that the site has a
    registration of its own, or that the organizer may give a link to their own service instead --
    and then cannot have what the site's timing and its photo recognition offer.
17. **The key and the spending.** The maintainer issued a DeepSeek key for the site,
    `ASSISTANT_LLM_API_KEY` in Render's environment, and reads its spending on DeepSeek's dashboard;
    the site counts nothing for now.
18. **Only the event.** Asked anything else -- to write code, say -- the assistant asks to keep to
    the event, so that the key is not spent on other work.
19. **The privacy policy** says that part of the conversation goes to a language model while an
    event is added or edited, without naming the provider: changing the model needs no new policy.
20. **No mark on a published announcement.** Drafted by a model or not, whoever publishes it
    answers for it.
21. **Calls to the model while building it** are allowed, sparingly.

Later the same day, on news and articles:

22. **Articles are not translated.** A knowledge article is written by hand, or through the API, in
    the language it belongs to.
23. **News get the assistant too**, for admins, on the pages where a news item is added and edited:
    it translates the item into the three languages, puts its formatting right and changes its text
    as the admin asks -- nothing invented. The conversation is kept with the news item, as an
    event's is with its event.
24. **One assistant, one key, skills by kind.** The same code and the same `ASSISTANT_LLM_API_KEY`
    serve both. What the assistant is told differs, and lives apart: `assistant/skills/event/` for
    events, `assistant/skills/news/` for news.
25. **#361 is settled by the two**: events and news are written in the three languages by the
    assistant, and articles need no translation.
26. **Only admins and up use the key**: every operation that reaches the model is tested against
    every role, by token and by the site's session.

Two days later, on 2026-10-31:

27. **Organizers too.** An event costs about a cent of the model, as read on the provider's
    dashboard, and the site has few users: the event assistant is opened to organizers and up, as
    decision 1 foresaw, and still without limits (decision 8). An organizer reaches only
    their own -- the conversations they started and those of their own events; whoever may edit an
    event sees its whole conversation, an admin's messages included. News stays with admins, who
    alone write it. Decisions 1 and 26 hold for news only.

## Requirements already fixed elsewhere

- **Constitution VI**: no local or sport-specific hardcoding -- what to ask for a race or a ride
  lives in the instructions and in the event types, the provider and the model in settings and in
  one constant.
- **Constitution VII**: what the chat does is also an API operation under `/api/v1/` for the same
  people (organizers and up; news: admins and up), with its tests.
- **The interface rules** (`.claude/skills/interface`): phone first -- on a phone the chat takes the
  lower part of the screen and can be folded to look at the form --, 44px targets, every word in
  three languages, nothing on the page moves unless the admin moved it.
- `specs/site/` (events, API, events agents) describes the feature as built.
