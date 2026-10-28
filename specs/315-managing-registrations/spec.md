# Feature Specification: Managing another member's registrations and event photos

**Feature Branch**: `315-managing-registrations`
**Created**: 2026-10-28
**Status**: Draft under discussion with the maintainer -- no implementation until the open questions
below are settled (the maintainer, 2026-10-28); the hand-over was agreed the same day (decisions 14-15)
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
14. **The hand-over: the manager's link, the member's consent, the manager's confirmation.**
    - The manager starts it: in the section of the people they manage, "Invite" gives a link with a
      key, to send wherever they like (a team chat).
    - Whoever opens it is asked to sign in (or sign up) first and is brought back to it; then a
      page names the manager and what they will be able to do, and the member presses "Allow".
    - The request waits in the manager's section under its own heading, with the member's last
      name, first name, team and year of birth, so the manager recognises their people without the
      site showing them anyone else; the manager accepts or rejects each request, or all at once
      ("Accept all", "Reject all").
    - A leaked link therefore fills only the waiting requests, never the list of people managed;
      and no link ever comes from the member's side, so nobody gains a member's registrations
      through a leak.
15. **The link's life.**
    - One link per manager at a time; it lasts a month, after which nobody can join through it
      even if the manager forgets it.
    - The manager may make a new one (the old one stops working) or delete it outright, as an
      event's upload token is deleted.
    - Making a new link, deleting it or letting it run out rejects no waiting request.
    - Opening a link that no longer works says so plainly: the link is not valid or has
      probably expired, and the person who sent it can make a new one.

## Open questions

1. **Several people at once, one fails** (a category that does not fit, the places run out): are
   the others registered and the failures shown, or nobody?
2. **A self-only event** (a registration tied to the participant's account): may a manager register
   a member there? Proposed: yes -- the registration still belongs to the member's account.
3. **What the member sees of their request:** proposed -- their section shows it as waiting for the
   manager, with a way to withdraw it; no email (decision 12 extends to this).
4. **A rejected request:** does the member see it was rejected, or does it just disappear? May they
   ask again through the same link (a stranger with a leaked link could keep asking until the
   manager deletes it)?
5. **When the link between two members ends:** proposed -- registrations the manager submitted stay
   the member's, untouched; the former manager loses every right over them and the member's photos.
6. **Opening one's own link, or the link of someone who already manages you:** proposed -- the page
   says so and asks nothing.

## Requirements already fixed elsewhere

- **#349 FR-024/FR-025**: a manager sees the albums of all their members' registrations and may
  mark photos ("this is me" / "not me") in them; a member sees and marks only their own; the link
  between them comes from this feature, never from names or teams. The "My photos" cabinet shows the
  manager one card per member's registration, titled with the member's name and bib.
- **Constitution VII**: every operation above -- the hand-over, the two lists, removing either way,
  registering a member, the photos -- is also an API operation under `/api/v1/` with the same rules,
  with tests that a member sees nothing of another member's albums and a stranger gets a 404.
- Update `specs/site/` (accounts, registrations, event photos) when the feature is built.
