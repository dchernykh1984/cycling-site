# Feature Specification: Managing another member's registrations and event photos

**Feature Branch**: `315-managing-registrations`
**Created**: 2026-10-28
**Status**: Draft under discussion with the maintainer -- no implementation until the open questions
below are settled (the maintainer, 2026-10-28)
**Issue**: [#315](https://github.com/dchernykh1984/cycling-site/issues/315) ("coach role"), with the
photo requirements [#349](https://github.com/dchernykh1984/cycling-site/issues/349) FR-024 and FR-025
**Input**: A coach, a parent or a team captain registers the people they look after for a start in
one go -- ticking them on the registration page -- and looks after those people's event photos.

## Decisions so far

Taken in conversation with the maintainer on 2026-10-28, in the order they came.

1. **Not a role.** Any member may manage another member's registrations and event photos with that
   member's consent. Nothing is added to the site's roles (participant, organizer, admin, owner):
   this is a link between two accounts, not a level of rights, so a coach is also anyone's
   managed member, and nobody asks for a role.
2. **The words.** The profile shows two sections named by what they do, with no "coach", "trainer"
   or "mentor" in them: the people who may manage my registrations and photos, and the people whose
   registrations and photos I manage. (Wording in three languages: to be written with the spec.)
3. **Consent by a button.** Agreeing to be managed takes a page that names who asks and what they
   will be able to do, and a button; opening a link alone never grants anything (a browser may
   prefetch a link, a page may embed it).
4. **Either side ends it.** The managed member removes a manager in their profile, and the manager
   removes a managed member in theirs. Agreeing to someone by mistake is undone that way.
5. **Self and chains.** Managing oneself is refused. Two members may manage each other. Rights do
   not pass along a chain: if A manages B and B manages C, A has no rights over C.
6. **An account each.** A managed member has an account of their own. A child without one is
   registered by a parent as today, in an event that allows registering anyone (its registration
   then belongs to the parent's account, and so does its photo album).
7. **No limits on the number** of managers a member has or members a manager manages (the
   maintainer sees no reason for one) -- unless the hand-over mechanism needs one against a
   leaked link (open question 1).
8. **What a manager may do:**
   - submit, change and cancel any registration of a managed member, including those the member
     submitted themselves;
   - see the member's event photo albums and mark photos in them, as #349 FR-025 describes
     (`event_photos.permissions.can_represent`, a stub returning False until now);
   - never change the member's profile.
9. **What a manager sees of a member:** a table in the section of the people they manage -- last
   name, first name, team and the other data a registration form takes. Not the whole profile; no
   email or phone.
10. **Registering several people.** The registration page offers checkboxes: the manager themselves
    and each managed member. For each person ticked, the standard registration form follows,
    filled in from that person's profile; the manager completes what is missing. What the manager
    types goes into the registration only, never back into the member's profile.
11. **Organizers see who submitted.** The participant list shows who submitted each registration,
    when at least one registration of the event was submitted by someone other than its
    participant.
12. **No email** when a manager registers a member (the site sends none for registrations today).
13. **Specification first.** This document and a plan are reviewed before any code.

## Open questions

1. **How the right is handed over.** Who starts it, and how a manager learns who a new member is
   without the site showing them all members. The maintainer's reasoning (2026-10-28): the
   manager's side should start it -- a leaked link of the manager's lets strangers flood their list
   with "members", while a leaked link of a member's would let strangers manage that member's
   registrations, which hurts far more. And the flood must not bury the manager's real members (a
   list of 20 swamped by thousands). It also has to stay simple enough for anyone to follow.
2. **Several people at once, one fails** (a category that does not fit, the places run out): are
   the others registered, and the failures shown, or nobody?
3. **A registration-only event** ("self only", tied to the participant's account): may a manager
   register a member there? Proposed: yes -- the registration still belongs to the member's account.
4. **Telling a member they gained a manager** (email or a line on the site) -- not decided; the
   no-email decision (12) is about registrations.

## Requirements already fixed elsewhere

- **#349 FR-024/FR-025**: a manager sees the albums of all their members' registrations and may
  mark photos ("this is me" / "not me") in them; a member sees and marks only their own; the link
  between them comes from this feature, never from names or teams. The "My photos" cabinet shows the
  manager one card per member's registration, titled with the member's name and bib.
- **Constitution VII**: every operation above -- the hand-over, the two lists, removing either way,
  registering a member, the photos -- is also an API operation under `/api/v1/` with the same rules,
  with tests that a member sees nothing of another member's albums and a stranger gets a 404.
- Update `specs/site/` (accounts, registrations, event photos) when the feature is built.
