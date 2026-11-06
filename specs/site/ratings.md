# Site Specification: Ratings

**Status**: Baseline -- describes the site as it works today
**Verified against**: branch `436-organizer-ratings` on 2026-11-06
**Code**: `ratings/` (models, form, rules, scores, digest, views, templates, template tags),
`api/endpoints/ratings.py`, `accounts/service_accounts.py`, `api/endpoints/service_accounts.py`,
`cycling_site/context_processors.py` (`review_requests`, `service_account_missing`),
`cycling_site/templates/_moderation_banner.html`
**Tests**: `tests/test_ratings_reviews.py`, `tests/test_ratings_organizers.py`, `tests/test_ratings_digest.py`,
`tests/test_service_accounts.py`, `tests/test_role_matrix.py` (`SERVICE_ACCOUNTS`), `tests/e2e/test_ratings.py`,
`tests/test_organizer_filter.py` (an organizer's name opens their events)
**Related**: [events](events.md), [accounts](accounts.md), [protocols](protocols.md),
[event photos](event-photos.md) (the bibs a start list gives); `specs/436-ratings/spec.md` (the decisions)

## Overview

The members who took part in an event rate it, anonymously, from the day after it; the organizer --
the member who posted it -- gets a public rating from their participants' scores, and the people who
edit an event read what its participants think: the figures and a digest the language model writes.
Nothing keeps who wrote a review.

## User Scenarios

### Story 1 -- Rate an event one took part in (P1)

1. **Given** a member whose own entry -- or the entry of a person without an account they added --
   has an active bib from the start list, and that bib in the event's protocol data with a result or
   any mark but `dns`, **When** the event's last day is over
   where it took place, **Then** every page shows "Rate the events you took part in" with the event,
   "Rate" and "Do not rate", until they answer; either answer brings them back to the page they were
   on. The banner holds two events at a time, the latest first; the rest come up as these are answered. On a phone each button takes a tap across 44 px, and in every skin reads 4.5:1 on the banner.
2. **Given** "Rate", **Then** a page asks an overall score from 1 to 5 (required) and a comment
   (optional), says the review is anonymous and so cannot be changed or deleted, and sends it or
   refuses; refusing is as final as a review and leaves the same mark. The chosen score shows as a
   pressed button, 3:1 apart from the others in every skin.
3. **Given** an event the site's agents posted, an event with HTML protocols only, a `dns`, a
   rejected entry or a bib in conflict, **Then** nobody is asked; for people without an account, the
   member who added them is asked once for the event, however many of them started. The event's
   author who entered it and started is asked as anyone else.
4. **Given** the API, **Then** `GET /ratings/pending` lists the events the caller may rate,
   `POST /ratings/events/{id}/review` takes `{"answers": {"overall": 1-5, "comment": ""}}` (422 for
   a wrong score, 409 when not allowed or answered) and `POST .../decline` refuses.

### Story 2 -- An organizer's rating (P1)

1. **Given** an organizer whose events' reviews hold three scores or more, **Then** the Ratings tab
   -- in the menu right after Calendar, in every skin -- lists them, the best average first, with the
   number of scores and of events, and each of their events' pages shows "Organizer's rating" with
   the average and the number of scores; with fewer, nothing shows. The average is of all their
   scores, each weighing the same whatever the size of its event. An organizer's name opens the
   calendar's list of all their events, past and to come (the Organizer filter, [calendar](calendar.md)).
2. **Given** a hidden, deleted or unapproved event, or one the site's agents posted, **Then** its
   reviews do not count. An event by invitation (issue #313) asks its participants and counts as any
   other.
3. **Given** the API, **Then** `GET /ratings/organizers` (no token) gives the same list.

### Story 3 -- What the participants think (P2)

1. **Given** someone who edits the event (its author, an admin, an owner), **Then** "What the
   participants think" by its edit buttons opens a page with the number of reviews and, from two
   reviews, the average, the spread of scores and a digest; anybody else finds no page.
2. **Given** "Write the digest", **Then** the language model the assistant uses gets the scores and
   comments shuffled, with nothing of their authors, and writes the points participants liked and
   would improve in the page's language; the digest is kept and written again only once more reviews
   came -- until then a request to write it gives the kept one, and the model is not asked. A model
   that does not answer leaves a message and nothing kept.
3. **Given** the API, **Then** `GET` and `POST /ratings/events/{id}/summary?language=` give and write
   it (403 for anyone else, 409 below two reviews, 503 when the model does not answer).
4. **Given** a member who posted events with two reviews or more, **Then** under the organizers'
   ratings the Ratings tab lists those events, the latest first, each with its number of reviews, a
   note when it has no digest yet or reviews came since, and a link to what its participants think;
   only one's own events, whatever the role. `GET /ratings/mine?language=` gives the same list.

### Story 4 -- The agents' account (P2)

1. **Given** an owner, **Then** the profile's "Service accounts" card offers the accounts with an
   API token, and those marked, and marks exactly the ticked ones; until one is marked, every page
   asks the owners to. The API has `GET /service-accounts/` and `PUT`/`DELETE /service-accounts/{id}`.

## Functional Requirements

- **FR-RAT-001**: A review (`Review`) keeps a random UUID, its event, the form version and the answers;
  an account keeps one `ReviewMark` per event answered, with no time; neither is in the audit log, and
  no page or admin screen shows a review as written.
- **FR-RAT-002**: The questions are `ratings.form.QUESTIONS`, versioned by `form.VERSION`; the score
  of the question that `counts` makes the organizer's rating.
- **FR-RAT-003**: Thresholds: an organizer's rating from `scores.PUBLIC_FROM` (3) scores; an event's
  figures and digest from `digest.DIGEST_FROM` (2) reviews.

## Key Entities

- **ReviewMark**: account, event (unique together).
- **Review**: UUID, event, form version, answers (JSON by question key).
- **ReviewSummary**: event, language, the number of reviews it was written from, text, when written.
- **User.is_service_account**: the account the site's agents post through.

## Local assumptions

- None known.

## API gaps

- None: rating, refusing, the organizers' list, the digest and the service accounts all have their
  operations.

## Open Questions

- A member who manages other members' accounts (issue #315) is not asked for them, as they have
  accounts to answer with; only people without an account are answered for.
