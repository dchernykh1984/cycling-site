---
name: virtual-members
description: People without accounts a member adds to enter them for races and look after their photos (issue 438) - the member's word, the limits, adding hundreds from a list in one request with the member's own token, entering them for races and naming their bibs. Read before adding or entering people for a member, by hand or from a list.
---

# People without accounts

A member -- a coach, a parent -- adds people who have no account on the site: the children of a
section, a family. Such a person (`accounts.models.VirtualMember`) belongs to the member who added
them and exists only in that member's profile card "People without an account" and in the API below.
The member enters them for races on the registration page, events that take only one's own data
included, and looks after their race photos: the albums of their entries and a bib named for them.
A person without an account is never turned into an account.

Everything below is done with **the member's own token**: profile, "API access", "Generate token",
then `Authorization: Bearer <token>`. The token is the member's; it goes into one command's
environment, never into a file, a commit or a reply.

## The member's word first

Until the member confirms that they may handle these people's personal data -- they have the
consent of the people or of their legal representatives -- nobody can be added. The card asks it
with the button "I am authorized to handle their personal data"; the API with
`POST /api/v1/virtual-members/consent` (204). It is given once and never taken back. Adding before
it answers 403 with the address to confirm at. Ask the member; never confirm on their behalf
because a list arrived.

## Limits

`accounts/roles.py`: an admin or an owner adds any number, an organizer 1000, a participant 10, a
guest none. `GET /api/v1/virtual-members/` answers `consented`, `limit` (null for any number),
`room` (how many more) and `people`.

## Adding many from a list

`POST /api/v1/virtual-members/` takes `{"people": [...], "dry_run": false}`, up to 1000 rows a
request. Each row: `last_name`, `first_name`, `gender` (`M` or `F`), `birth_date` (`YYYY-MM-DD`),
optional `team`, `city`, `strava_link` (a profile's URL, filled into an event that asks for one)
and `sports_achievements` (a sports rank or category, or the like, as the source writes it).

- **Whole or not at all.** Every row is checked first. A row with a mistake, or more new people
  than `room`, saves nobody: 422 with `detail` and `rows: [{row, errors}]`, rows counted from 0.
- **Sent twice, added once.** A row with the same last name, first name and date of birth as
  somebody already added (letters' case aside) is left as it is and comes back in `existing`;
  the new ones come back in `created` with their ids.
- **`dry_run: true`** checks the batch and says what it would do, saving nothing (`id` 0).

A list from a member -- a spreadsheet, a chat message, a photo of a sheet -- becomes rows exactly as
it stands. **Nothing is made up**: a row without a gender or a full date of birth goes back to the
member as a question, and so does a name that could be read two ways. Then:

1. `GET /api/v1/virtual-members/`: has the member given their word, and is there `room` for the list?
2. Send the batch with `"dry_run": true`; fix the rows a 422 names, with the member's answers.
3. Send it again without `dry_run`.
4. Tell the member how many were created and how many were there already, by name.

```bash
curl -s -X POST "$SITE/api/v1/virtual-members/" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d @people.json
```

`PATCH /api/v1/virtual-members/{id}` changes a person (409 when the change makes them a copy of
somebody already added); `DELETE /api/v1/virtual-members/{id}` deletes one: their entries in races
that have not started are cancelled, while past races, a race run today and a stage race under way
keep them. Deleting the member's account deletes
the people they added.

## Entering them for a race

`POST /api/v1/registrations/` with `{"competition_id": N, "entries": [...]}` does what the
registration page does for the people ticked on it, one entry after another, each with its own
answer `{row, registration_id, errors}`: an entry refused says why and the next is still tried.

- `person` names whom: `me`, `member:<id>` (a member whose registrations the caller manages),
  `virtual:<id>` (a person without an account the caller added), or `other` -- another person typed
  in, only where the event lets anyone be entered.
- The rest is the event's form -- `category_id`, `team`, `city`, `additional_info`, names, `gender`,
  `birth_date` or `birth_year` -- and is filled in from the person when left out, the first category
  they fit included. Where the event's additional field is the date of birth, it is `YYYY-MM-DD`, from the
  person's account when left out. An event that takes only one's own data takes the names, gender and date of
  birth from the person, whatever the entry says.
- An event with categories enters nobody without one: a person no open category takes is refused,
  and `errors.category` says so -- tell the member, never pick another category for them.
- 404 for an event the caller cannot see, 409 while its registration is closed or for a relay.

`GET /api/v1/registrations/` lists the caller's entries and those of the people they enter
(`?competition_id=` narrows it); `PATCH` and `DELETE /api/v1/registrations/{id}` change and cancel one
while registration is open.

## Their photos

The albums of their entries are in `GET /api/v1/event-photos/me/registrations`, as the member's own
are. Where the start lists give no bib, the member names one:
`PUT /api/v1/event-photos/competitions/{id}/my-bib` with `{"bib": "7", "person": <id>}`, and takes it
back with `DELETE .../my-bib?person=<id>`; `GET /api/v1/event-photos/me/declared-bibs` lists them,
`person` naming whose.

## Privacy

The policy (`/privacy/`) says the member answers for having the people's consent, that only the
member sees and changes these people's data on the site, and what happens when a person or the
member's account is deleted. A change to what the feature keeps or shows changes that paragraph too.
