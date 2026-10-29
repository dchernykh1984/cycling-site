# Site Specification: Accounts, roles and the profile

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21; managing another member's registrations (issue #315) against branch `315-managing-registrations` on 2026-10-28
**Code**: `accounts/` (models, views, adapters, access, signals, managing), `cycling_site/templates/allauth/`,
`api/endpoints/managing.py`
**Tests**: `accounts/tests.py`, `tests/test_role_request.py`, `tests/test_user_display.py`,
`tests/test_oauth_callback.py`, `tests/test_save_filter_preferences.py`, `tests/test_skin_choice.py`,
`tests/e2e/test_api_token_profile.py`, `tests/e2e/test_profile_preferences.py`,
`tests/e2e/test_theme_choice.py`, `tests/test_virtual_ride_api.py`, `tests/test_managing.py`,
`tests/test_managing_api.py`, `tests/e2e/test_managing.py`
**Related**: [setup hints](site-shell.md), [skins](skins.md), [registrations](registrations.md)

## Overview

Anyone can read the site. Signing in -- by e-mail and password, or with Google, GitHub or Strava
-- makes a member, whose rights grow along a ladder of five roles. The profile is the member's
cabinet: their data for race registration, their events and registrations, the defaults the
calendar opens with, their skin, their API token, and the ways to reach the site's owners.

## User Scenarios

### Story 1 -- Join and confirm (P1)

A visitor signs up with an e-mail and a password, or through a provider, and can use the site at
once; confirming the address unlocks everything that writes.

1. **Given** a visitor signs up with an e-mail, **When** the form is sent, **Then** they are signed
   in as a **guest** and a confirmation mail is sent.
2. **Given** the address is already registered, **When** someone signs up with it, **Then** the
   response does not reveal that an account exists.
3. **Given** a guest confirms their address, **Then** they become a **participant**; a higher role
   is never lowered by a confirmation.
4. **Given** a provider returns a verified e-mail, **Then** the member becomes a participant at
   once; an unverified or missing e-mail leaves them a guest.
5. **Given** a guest asks for the confirmation again, **Then** one mail goes out at most once a
   minute; a failed send frees the slot again.

### Story 2 -- Keep the data registration needs (P1)

1. **Given** a member edits their profile, **Then** first and last name, gender, birth date, team,
   city and Strava link are saved and shown on the profile.
2. **Given** a member signed up with Strava, **Then** their Strava profile link is filled from the
   athlete id, unless they already set one.
3. **Given** the page is Russian, **Then** the birth date field is still prefilled in ISO form.

### Story 3 -- Sign-in methods (P2)

1. **Given** a member opens the profile, **Then** a card lists e-mail/password and every
   configured provider (in settings order), each connected or not, linking to the connections
   page; a member with a password is offered "change", one without "set", one without an address
   is asked to add one first.
2. **Given** a member tries to disconnect their last way in, **Then** it is refused: a password
   counts only together with an e-mail address.
3. **Given** a provider callback, **Then** the address sent to and received from the provider has
   no language prefix, whatever language the sign-in started from.

### Story 4 -- The role ladder (P2)

1. **Given** a participant opens the profile, **Then** they see all five roles weakest first,
   their own in bold, and a button to ask for another one (higher or lower); a guest sees the
   ladder without the button.
2. **Given** a member asks for a role, **Then** a reason is required, the owners get a mail (in
   English whatever the page language), nothing is granted, and further requests wait a minute.

### Story 5 -- Reach the owners (P3)

1. **Given** a participant writes to the owners, **Then** the message (required, up to 5000
   characters; subject up to 200, newlines collapsed) is mailed to the owners' mailbox in English;
   a second message within a minute is refused with a countdown on the button; a mail-server
   failure is logged, shows a message, and frees the slot.
2. **Given** a guest or a visitor, **Then** the contact form is not offered.

### Story 6 -- Defaults, skin and API (P3)

1. **Given** a member saves preferred locations, directions/disciplines and event types, **Then**
   the calendar, list and map open with them; clearing a picker clears that preference.
2. **Given** "always save the filter" is on, **Then** a filter changed on a calendar page is saved
   as the preference straight away instead of offering a save button, and "Reset" saves the cleared
   filter before the page leaves (three seconds at most), so the old one cannot stay behind.
3. **Given** a participant or higher, **Then** the profile shows an API section where a token can
   be generated; regenerating invalidates the old one; guests get no API section.
4. **Given** a member picks a skin, **Then** it is kept in their profile (see [skins](skins.md)).
5. **Given** a member has finished rides on the virtual ride page, **Then** the profile shows their
   totals, best time per route with attempts, peak power over 5 s, 1, 5 and 20 min, top speed and the
   latest rides; demo rides are listed but never count ([site shell](site-shell.md)).

### Story 7 -- Manage another member's registrations and photos (P2)

A coach, a parent or a team captain looks after other members' registrations and race photos, with
their consent. Not a role: a link between two accounts (issue #315; the decisions are in
`specs/315-managing-registrations/spec.md`).

1. **Given** a confirmed member, **Then** the profile shows "Who may manage my registrations and
   photos" and "Whose registrations and photos I manage", in one card ("Managing registrations and
   photos") between the sign-in methods and the role; nothing names a role.
2. **Given** "Create link", **Then** the member (the manager) gets a link with a key, valid for 30
   days, with the site's share button; "New link" makes the old one stop working and "Delete link"
   removes it; neither, nor its running out, rejects a request waiting. A link run out says when.
   A member with no first and last name in the profile is asked for them first: whoever opens the
   link has to see who asks.
3. **Given** someone opens the link, **Then** a visitor signs in first and comes back, and an
   unconfirmed account is told, on the page, to confirm the address and open the link again (sent
   away to the profile, it would lose the link); the page names the manager, what they may do
   (register the member, change and cancel their registrations, see their race photos and mark
   them) and what they will see (last name, first name, date of birth, gender, city, team, and the
   Strava link an event's form may take -- not the e-mail), and asks by an "Allow" button. Opening
   it grants nothing. A key that is not valid or ran out: a 404 saying so; one's own link, a
   manager already, a request already waiting: a plain message.
4. **Given** "Allow", **Then** the request waits in the manager's section with the member's last
   name, first name, team and year of birth; the manager accepts or rejects each, or all at once. A
   rejected request disappears and may be sent again. The member sees it waiting, with "Withdraw".
5. **Given** an accepted link, **Then** the manager sees the member's last name, first name, date
   of birth, gender, city and team, and acts for them in registrations
   ([registrations](registrations.md)) and race photos ([event photos](event-photos.md)); never on
   the profile.
6. **Given** either side removes the other, **Then** nothing is left: the former manager sees and
   may do nothing of the member's; the registrations they submitted stay the member's.
7. Rights never pass along a chain (A manages B and B manages C: A has nothing of C's); two members
   may manage each other; nobody manages themselves. No mail is sent anywhere in this.

### Edge Cases

- An unverified member (guest) can open the profile, but sees a minimal cabinet: profile data, the
  confirmation block, the sign-in methods and the role ladder (without the request button); the
  contact, appearance, registrations, submitted events, submissions, managing and API sections are
  hidden.
- The managing sections show each member and each request as a card, every column named beside its
  value, at every width: the profile's column is too narrow for their columns even on a desktop.
- Anything that writes -- submitting, registering, commenting, contacting the owners, the API --
  sends a guest to their profile with a message asking to confirm the address.
- A member's public name never exposes their e-mail; where a name is shown to them (the sign-in
  greeting) it is the profile name, then the sign-in address, then the username.

## Functional Requirements

- **FR-ACC-001**: Roles, weakest first: guest, participant, organizer, admin, owner. A new account
  is a guest. An owner is always staff and superuser.
- **FR-ACC-002**: A guest becomes a participant when an e-mail is confirmed or a provider returns a
  verified e-mail. No other role is granted automatically.
- **FR-ACC-003**: Only organizer and above assign roles, and only up to their own rank; the
  participant role is assigned by hand only by admin and above; a superuser may assign any role.
  A member manages only users of rank not above their own. Django admin and the Wagtail user views
  enforce the same rules (no escalation to owner or superuser by an admin; no copy view).
- **FR-ACC-004**: Role groups follow the role: participant and above have a managed group of that
  role, guests none; a role change swaps the group.
- **FR-ACC-005**: Writes are open to participant and above (`ParticipantRequiredMixin`); a guest is
  redirected to the profile with the confirmation message.
- **FR-ACC-006**: One mail per member per minute across the confirmation resend, the contact form
  and the role request; the slot is reserved before sending and released on failure.
- **FR-ACC-007**: Strava sign-in requests read-only scope only and keeps no token. Sending virtual
  rides to Strava is a separate grant (`read,activity:write`) the member gives from the profile's
  "Virtual rides" card with Strava's own "Connect with Strava" button; its tokens live in
  `trainer.StravaConnection`, are refreshed when they expire, and are revoked at Strava and deleted
  when the member disconnects it there or through the API, or their account is deleted. Nothing
  reads the member's Strava activities.
- **FR-ACC-008**: The profile lists the member's own submitted events (those needing attention
  first) and their registrations: open entries as cards with approval and payment badges as their
  event requires -- with those of the members they manage, under the member's name -- and every own
  entry in a table below that marks only the rejected, waiting and unpaid ones (see
  [registrations](registrations.md)); other registrations, those of deleted events, or not tied to a
  user are not shown.
- **FR-ACC-009**: A member's chosen interface language is remembered when they switch language.
- **FR-ACC-010**: Every form and API request string is length-bounded or validated elsewhere
  (`tests/test_input_length_limits.py` keeps the registry complete).
- **FR-ACC-011**: Managing (issue #315): one link per manager, valid for 30 days from when it was
  made; a request (`ManagedMember`) waits until the manager accepts it and gives rights only then
  (`accounts.managing.acts_for`); rejecting it, or either side ending an accepted one, deletes it.
  Every rule lives in `accounts/managing.py`, which the pages and `/api/v1/managing/` share.

## Key Entities

- **User**: role, profile data (names, gender, birth date, team, city, Strava link), preferred
  locations / directions / disciplines / event types, autosave flag, skin (`theme`), preferred
  language, API token, dismissed setup hints, time of the last mail sent on their behalf.
- **E-mail address / social account** (allauth): the ways a member signs in.
- **Virtual ride** (`trainer.VirtualRide`): one finished ride with its route key and name, kind
  (race, cadence plan, free ride), times, distance, power and its source, place, peak powers; the
  records are computed from these, never stored. Its track (`trainer.RideTrack`, a point a second:
  time, the route's place on the map, height, distance, speed, power, cadence, pulse) and what
  became of it at Strava (`trainer.StravaUpload`: processing, the activity, or the reason).
- **Strava connection** (`trainer.StravaConnection`): the member's upload grant, one per member.
- **Manager's link** (`accounts.ManagerInvite`): a member's key for the people they will manage, one
  per member, and when it was made.
- **Managed member** (`accounts.ManagedMember`): manager, member, when asked, when accepted (empty
  while it waits); one per pair, never one's own.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: Strava is the sport's de facto standard; a general tracker connector may come later, not as a fix). Strava is the one activity-tracking service the profile knows: a "Strava link" field, filled from
  a Strava sign-in (`accounts/adapters.py`), and a setup hint asking for it. Other trackers
  (Garmin Connect, Polar, Suunto and the like) have no place yet.
- The sign-in providers (Google, GitHub, Strava) come from settings, which is as it should be.

## API gaps

- Editing the profile (names, gender, birth date, team, city, Strava link).
- Asking for another role and writing to the owners.
- **Exception**: signing up, signing in, confirming the address, connecting sign-in providers,
  connecting Strava for uploads (a browser round trip through Strava) and generating the API token. They establish who an API caller is, so they come before the API
  rather than through it.
- **Exception**: the skin, saved calendar filters and dismissed setup hints. They only change how
  the site's own pages look and open, so a program has nothing to do with them.

## Open Questions

- None known.
