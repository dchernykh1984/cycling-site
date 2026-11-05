# Feature Specification: People without accounts, and the registration page for many

**Feature Branch**: `438-virtual-members`
**Created**: 2026-11-05
**Status**: Agreed with the maintainer in conversation on 2026-11-05 and built on that branch; the
maintainer asked for the code straight away, so no plan was reviewed before it
**Issues**: [#438](https://github.com/dchernykh1984/cycling-site/issues/438) (people without accounts,
the registration API, the privacy question), [#439](https://github.com/dchernykh1984/cycling-site/issues/439)
(a tick chooses, a button opens the details), [#440](https://github.com/dchernykh1984/cycling-site/issues/440)
(filters on the registration page)
**Input**: A coach of a children's section enters the children for races and looks after their race
photos, though the children have no accounts; the registration page for many people becomes a list
one can work through, with the same done over the API.

## Decisions

Taken with the maintainer on 2026-11-05.

1. **A person of their own kind.** People without accounts are needed only for entries and photos,
   so they are not accounts: `accounts.VirtualMember`, owned by the member who added them and found
   only in that member's profile and API. They have no profile and never sign in.
2. **No claiming.** A person without an account is never turned into an account (perhaps one day,
   not now).
3. **The member's word.** Until the member presses "I am authorized to handle their personal data"
   the card holds only what it is for and that button; the API takes the same word. It cannot be
   taken back.
4. **Limits by role.** Admins and owners add any number, organizers 1000, participants 10 ("the
   others sign up themselves and join as managed members"). A section usually has up to a hundred.
5. **Deleting.** A person deleted -- alone, or with the member's account -- takes their entries in
   races to come with them; entries in past races stay in the results.
6. **Entries.** The member enters them as they enter a member they manage (issue #315), events that
   take only one's own data included, from the person's own names, gender and date of birth.
7. **Photos.** Both ways: the albums of the person's entries, with "this is me / not me" marks, and a
   bib the member names for them where the start lists give none, as a member names their own.
8. **The card.** It folds away, and has filters: a last or first name in any script, as the place
   menus do, a team, a span of dates of birth from and to.
9. **Many at once.** The API adds a whole list in one request with the member's own token, so that
   hundreds come from one request to an AI agent; a skill (`virtual-members`, for both agents) says
   how.
10. **The registration API.** Entering, changing, cancelling and listing entries with one's own
    token, for oneself, the members one manages and the people one added -- the gap
    `specs/site/registrations.md` listed.
11. **Privacy.** A tick "I agree with the privacy policy" on the sign-up form; an account Google,
    GitHub or Strava made is asked the same at its first sign-in; members from before are not asked.
    The policy says that whoever adds people without accounts answers for the permission to handle
    their personal data.
12. **The registration page (#439).** A tick chooses a person; opening their details is a button of
    its own. Details are folded; after a send, those of whoever could not be entered open by
    themselves.
13. **Filters there (#440).** By surname in any script, by team, and by the event's categories as a
    menu of boxes (a category has genders and a span of birth dates); a line says how many are
    ticked and how many of them the filters hide.

## User Scenarios

### Story 1 -- A coach adds the section (P1)

1. **Given** a confirmed member's profile, **Then** a card "People without an account" asks for
   their word first; once given, it counts the people against the role's limit and adds one at a
   time, or a list through the API in one request -- whole or not at all, `dry_run` to check first,
   anybody added already left as they are.
2. **Given** a long list in the card, **Then** the filters narrow it by name, team and dates of birth.
3. **Given** a person changed, **Then** entries made from then on carry the change; entries made
   already keep what they were made with.

### Story 2 -- The coach enters them for a race (P1)

1. **Given** the registration page of an event that is not a relay, **Then** the people added are
   listed after the members the coach manages, marked "no account"; ticking enters them with their
   own data, folded details and all.
2. **Given** six people or more, **Then** filters by name, team and category narrow the list; what is
   hidden but ticked is still sent, and a line says so.
3. **Given** the API, **Then** the same entries go in one request (`POST /api/v1/registrations/`),
   each with its own answer.

### Story 3 -- Their photos (P2)

1. **Given** an event with an indexed album, **Then** the coach sees and marks the albums of the
   people's entries, and names a bib for a person where the start lists bound none.

### Story 4 -- A new member is asked about privacy (P2)

1. **Given** the sign-up form, **Then** its last field is the privacy question, and no account is
   made without the tick.
2. **Given** an account a provider made, **Then** its first sign-in asks the same before any page.

## Functional Requirements

- **FR-438-001**: A person without an account belongs to one member, who alone reaches them on the
  site: the profile card, the registration page, the photo pages and `/api/v1/virtual-members/`.
- **FR-438-002**: Adding takes the member's word (once, never withdrawn) and room under the limit of
  their role (`accounts.roles.virtual_members_limit`). One person per last name, first name and date
  of birth for a member, letters' case aside.
- **FR-438-003**: A batch is checked whole before anything is saved: a row with a mistake, or more
  new people than the room, saves nobody and names every row's errors.
- **FR-438-004**: Deleting a person cancels their entries in races that have not started; a race run
  today or a stage race under way keeps them, as past races do. The member's account deleted deletes
  the people they added.
- **FR-438-005**: An entry for a person without an account keeps the person and the member who
  submitted it, never an account, and lets nobody into an invite-only event.
- **FR-438-006**: The registration page's details open by a button of their own and stay folded;
  those of a person a send refused open; without a script all stand open.
- **FR-438-007**: From `registering.FILTERED_FROM` people the registration page offers filters that
  only change what is shown.
- **FR-438-008**: `/api/v1/registrations/` follows the page's rules through the page's own forms and
  functions (`registrations.registering`).
- **FR-438-009**: Every new member answers the privacy question once: on the sign-up form, or at a
  provider's first sign-in, before any page but the policy, the terms and signing out.

## Key Entities

- **Person without an account** (`accounts.VirtualMember`): owner, last name, first name, gender,
  date of birth, team, city.
- **User**: when they agreed with the privacy policy, whether a provider's account waits to be asked,
  when they gave their word for the people they add.
- **CompetitionRegistration** and **DeclaredBib**: each now names either an account or a person
  without one.

## Local assumptions

- None: the limits are by role, the providers come from settings, and nothing names a place or a
  sport.

## Out of scope

- Turning a person without an account into an account.
- A person without an account in a relay team.

## Open Questions

- A member who does not agree at a provider's first sign-in keeps the account the provider made,
  with the name it brought, but can open no page until they agree; the site has no way for them to
  delete it themselves (`NEEDS CLARIFICATION`: whether the question page should offer one).
