# Feature Specification: Ratings -- the organizers' first

**Issue**: #436
**Status**: Built (organizers' ratings); the participants' ratings are not started
**Decided with the maintainer**: 2026-11-06, in conversation; recorded here

## Scope

The issue asks for the participants' ratings and the organizers'. The organizers' come first: the
ability to rate an event, the request to rate it, the organizer's public rating and a digest of the
reviews for the event's editors. The participants' ratings (a model over results, splits by sport)
are a later piece of work and are not described here.

## Decisions

1. **Who is rated.** The member who posted the event (`Competition.submitted_by`). When an admin
   posts an event for another club, an owner re-assigns its author in the Django admin, which also
   gives that member the author's rights over the event.
2. **The agents' account.** An owner marks it in their profile (or through the API); until one is
   marked, every page asks the owners to. Its events carry no organizer's rating and ask nobody.
3. **Who may rate.** A member whose own entry was given a bib by the start list (Start Protocol
   Maker's `r<id>` field, `IssuedBib`, active) and whose bib the event's protocol data lists with a
   result or with any mark but `dns` -- a DNF or a DSQ rates too. An event with HTML protocols only
   asks nobody. An organizer who entered their own event and started rates it as anyone else does
   (the maintainer, 2026-11-06). People without an account do not rate; handed over to
   an account of their own, they can. Until then the member who added and entered them -- their
   coach, in effect -- is asked instead, once for the event however many of them started: such a
   person is a small child, whose view of the organization is not one to weigh, or one who did not
   bother to sign up, whose view counts for no more than one participant's. A member who manages
   other members' accounts is not asked for them: they have accounts to answer with.
4. **When.** From the day after the event's last day, by the calendar of the event's own place --
   not on the day, in the heat of it -- and then on every page, with no end, until the member rates
   or refuses. The early events, held long ago, are wanted too. The banner asks about two events at a
   time, the latest first, the one remembered best; the others come up as these are answered.
5. **What a review is.** An overall score from 1 to 5, required, and a comment, optional. The form
   is one versioned list of questions (`ratings/form.py`); a review keeps its answers by key with the
   version, so a score for another parameter can be added later without touching earlier reviews.
6. **Anonymity.** The account keeps one mark per event -- that it answered, with a review or with a
   refusal, which cannot be told apart -- and no time. A review keeps a random id, its event, the form
   version and the answers: no author, no time; neither is audited. A review cannot be changed or
   deleted. The maintainer accepted that someone with the database could still try to pair a mark
   with a review by the transactions that wrote them; what they would learn is not sensitive.
7. **Nobody reads a review as written** on the site, the owners included: no page and no admin screen
   shows one. The language model reads them for the digest.
8. **The organizer's rating** is the average overall score over all their events' reviews, public
   from three scores: on the Ratings tab (between Calendar and Map) and beside each of their events.
9. **The digest** -- what the participants think of one event -- is for the people who edit the event:
   its author, the admins and the owners. It shows from two reviews: the count, the average, the
   spread of scores, and a text the language model writes from the scores and the comments, by a
   button, kept, and written again only once more reviews came.
10. **No split by sport** for the organizers: the questions are about the organization, and smaller
    cells would make an author easier to guess. Each review keeps its event, so a split by direction
    can be added later as a filter.
11. **Finding the digests** (the maintainer, 2026-11-06): under the organizers' ratings, whoever posted
    events with reviews enough for a digest (two) sees those events, each linking to what its
    participants think. Only one's own events, admins and owners included: they may edit every event,
    and all of them would bury their own.

## Not built

- The participants' ratings (issue #436, parts 1 and 5).
- A complaint button of its own: a participant removed from a protocol writes to the owners through
  the existing contact form.
