# Feature Specification: An assistant that adds an event by asking about it

**Feature Branch**: `353-assistant`
**Created**: 2026-10-29
**Status**: Draft for the maintainer's review; no plan and no code yet
**Issue**: [#353](https://github.com/dchernykh1984/cycling-site/issues/353); it also settles
[#361](https://github.com/dchernykh1984/cycling-site/issues/361) (machine translation of the locales)
for events
**Input**: An admin tells a chat what event they want to add; the chat asks what a rider needs to
know, fills the event's form on the page in three languages, and leaves the publishing to the admin.

## Decisions so far

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
   presses the form's own button; the assistant writes nothing to the site itself.
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
8. **No limits for admins.** There are few of them, and a spend is someone's. Each call's tokens
   are counted per admin, to decide about organizers on numbers.
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

## Open questions

1. **What the assistant must ask** (NEEDS CLARIFICATION, in part). For a ride, decision 11 holds
   what an announcement must say; still open, from the draft offered on 2026-10-29: distance,
   climbing and surface; the pace and whether the group waits; who leads and where a cancellation
   is announced. For a race the draft stands, the maintainer's list wanted: the date and start
   times by distance; start and finish on the map; distances and categories; registration (link,
   deadline, fee); the regulations; the course.
2. **Where the conversation is kept.** Proposed: in the browser tab only, nothing of it on the
   server but the token counts of item 8.
3. **Which key.** Proposed: a DeepSeek key of the site's own, apart from the agents', so that its
   spending can be told apart and the key revoked alone.
4. **Editing an existing event** through the chat, on its edit page: in the first version, or later?
5. **Registration on the site and race categories**: in the first version the assistant would put
   them into the description and the admin would switch registration on by hand. Agreed?
6. **The privacy policy** needs a line saying the chat's text goes to the model's provider; the
   wording is the maintainer's.

## Requirements already fixed elsewhere

- **Constitution VI**: no local or sport-specific hardcoding -- what to ask for a race or a ride
  lives in the instructions and in the event types, the provider and the model in settings and in
  one constant.
- **Constitution VII**: what the chat does is also an API operation under `/api/v1/` for the same
  people (admins and the owner), with its tests.
- **The interface rules** (`.claude/skills/interface`): phone first -- on a phone the chat takes the
  lower part of the screen and can be folded to look at the form --, 44px targets, every word in
  three languages, nothing on the page moves unless the admin moved it.
- `specs/site/` (events, API, events agents) describes the feature as built.
