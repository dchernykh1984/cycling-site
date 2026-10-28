# Implementation Plan: Managing another member's registrations and event photos

**Branch**: `315-managing-registrations` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)
**Status**: Built in pull request #402; the plan was reviewed four times before any code.

## Summary

A consented link between two accounts, not a role. A member (the *manager*) hands out a link; whoever
opens it signed in may ask to be managed, and the request waits until the manager accepts it. An
accepted link lets the manager enter the member for events, change and cancel the member's entries,
and see and mark the member's race photos -- on the site and through `/api/v1/`. Either side ends it,
and nothing is left behind. Words in the code: *manager* manages, *member* is managed.

## Technical Context

**Stack**: Django 6, django-ninja, gettext (ru / kk / en). No new dependency.
**Storage**: two tables in `accounts` (migration `0023_managed_members`).
**Testing**: pytest unit tests per layer, Playwright for the link's way between two profiles,
registering several people, and the sizes on a phone.

## Constitution Check

- **VI (no local hardcoding)**: nothing local or sport-specific; the link's lifetime is a constant
  of the model (30 days, the maintainer's decision 15).
- **VII (API by default)**: every operation of the two profile sections and of the link's page is an
  API operation under `/api/v1/managing/`; the photo rights reach `/api/v1/event-photos/` through
  `can_represent`. Entering a race through the API was a recorded gap before this feature and stays
  one, now for the members one manages too (`specs/site/registrations.md`).
- **XI (the API only grows)**: one router added, nothing changed or removed.

## Design

### Data (`accounts/models.py`, `accounts/managing.py`)

- `ManagerInvite`: one per manager (`OneToOneField`), a UUID key, `created_at`; valid for
  `LIFETIME` (30 days). A new link is the same row with a new key and time; deleting removes the
  row. Neither, nor expiry, touches the requests waiting.
- `ManagedMember`: `(manager, member)` unique, never one's own (check constraint);
  `accepted_at` empty while it waits. Rejecting and ending delete the row.
- `accounts/managing.py` holds every rule: `acts_for` (accepted only, never along a chain),
  `member_ids`, `issue_invite`, `delete_invite`, `find_invite` (live only), `outcome_for` / `ask`
  (asked, invalid, own, managed, waiting), `refusal` (the words for each), `accept`, `reject`,
  `accept_all`, `reject_all`, `drop` (the manager ends it), `leave` (the member ends or withdraws).

### Pages

- The link's page, `/<lang>/accounts/managing/join/<key>/` (`JoinManagerView`): a visitor signs in
  first and comes back; an unconfirmed account is told there to confirm the address and open the link
  again, and cannot answer until then. GET only shows: who asks, what they
  may do and see, and "Allow"; POST asks and goes to the profile's `#my-managers`. An invalid or
  expired key is a 404 with the plain message; one's own link, a manager already, a request already
  waiting: a banner.
- The profile (`accounts/_managing.html`): "Who may manage my registrations and photos"
  (`#my-managers`: each manager, "waiting for confirmation" and "Withdraw", or "Remove") and "Whose
  registrations and photos I manage" (`#managed-members`: the members' table, the requests waiting
  with one-by-one and all-at-once answers, the link with the site's share button, its date, "New
  link" and "Delete link"). Tables become cards on a phone. Buttons are POSTs to
  `accounts/managing/...` (`ManagingActionView`), each reaching only the reader's own rows.
- Registering (`registrations/registering.py`): entering one person is one function,
  `register_one`, called by the page for one and the page for several. The page for several
  (`register_many.html`) appears when the reader manages someone and the event is not a relay: the
  reader, then the members by last name, leaving out whoever is entered already unless the event takes
  several entries; a member whose profile cannot fill a self-only form has no checkbox and a note;
  where anyone may be entered, "Another person" too. A ticked person's form shows below their name
  (CSS `:has`); people are entered from the top, as many as can be; the page comes back with those
  entered marked and the reasons of the others. Only the reader, their members and "another person"
  may be ticked: anything else is a 403. In an invite-only event a member entered by their manager
  gets the event's invitation.
- Members' entries: `can_self_edit` lets the manager edit and cancel them on the owner's terms; the
  participant list offers the buttons on them and shows them to the manager even when hidden until
  approved; the profile's "Active registrations" lists them under the member's name; organizers read
  "Submitted by" under the registration date of an entry submitted by someone other than its
  participant (a line in a cell: the organizer's table has no room for another column).
- Photos: `can_represent` is `acts_for`; "My race photos", the event's registration cards and
  `GET /event-photos/me/registrations` list the members' registrations too.

### API (`api/endpoints/managing.py`, mounted at `/api/v1/managing/`)

`GET /` (the live link, managers, requests waiting, members), `POST /invite`, `DELETE /invite`,
`POST /join {key}` (404 invalid or expired, 409 own, managed or waiting, with the page's words),
`POST /waiting/{user_id}/accept`, `/reject`, `POST /waiting/accept-all`, `/reject-all`,
`DELETE /members/{user_id}`, `DELETE /managers/{user_id}`. `member_auth` (a confirmed member's
session or token) moved to `api/auth.py` and is shared with the virtual ride.

## Risks, and what was done about them

- The registration page: the page for one keeps its ids, names and behaviour (its HTML compared
  before and after the partials, its unit and browser tests run before and after).
- Personal data: a manager sees what a registration form takes, never the e-mail; a request waiting
  shows only what tells the member apart (names, team, year of birth).
- Found while building and fixed in their own commits: the registration page lost its category list
  data and the relay team after a refused entry; its refusals and its category list's first line
  were not translated.
