"""Who may do what on the site by role: the one place that compares roles.

Roles are cumulative (specs/site/accounts.md, FR-ACC-001): each holds everything the roles below it
may do, so a rule names the least role it needs. A superuser holds every role -- the owner always is
one (``User.save``) -- wherever ``at_least`` asks; ``role_at_least`` asks about the role alone, as a
few places always have. Whose an object is -- an event's author, a conversation's -- is decided where
the object lives (``calendar_app.visibility``, ``assistant.conversations``), on top of these.
``tests/test_role_matrix.py`` pins what every kind of visitor may do.

In a template: ``{% load roles %}`` and ``user|at_least:ROLES.MODERATE_EVENTS`` or
``user|role_at_least:ROLES.Role.PARTICIPANT``; every page has ``ROLES``.
"""

from __future__ import annotations

from accounts.models import User

Role = User.Role

# The least role for each rule the site checks in more than one place, so that one line moves it.

# Events (specs/site/events.md, FR-EVT-002).
PUBLISH_EVENTS = Role.ORGANIZER  # publish at once, switch registration on, manage one's own events
MODERATE_EVENTS = Role.ORGANIZER  # approve or reject anybody's event
MANAGE_ALL_EVENTS = Role.ADMIN  # every event: hidden, invite-only, reported, deleted
MARK_TOP_EVENTS = Role.ADMIN
EVENT_ASSISTANT = Role.ORGANIZER  # it spends the site's key (specs/353-event-assistant, decision 27)
SEE_ANY_CONVERSATION = Role.ADMIN  # an assistant conversation somebody else started

# What the site writes for everybody (specs/site/news-and-knowledge.md).
MANAGE_NEWS = Role.ADMIN  # write, edit, hide and delete news, take submitted news, delete comments
MANAGE_KNOWLEDGE = Role.ADMIN  # the same for knowledge articles
SUBMIT_KNOWLEDGE = Role.PARTICIPANT  # a draft article that waits for review
COMMENT = Role.PARTICIPANT

# Places (specs/site/locations.md). Approving geography is a rung above moderating events, so that
# approving an event never quietly approves the region and the city proposed with it.
APPROVE_PLACES = Role.ADMIN  # approve or reject a proposed place, see hidden ones, use a pending one
ADD_PLACES = Role.ORGANIZER  # a venue published at once; a region or a city proposed
PROPOSE_PLACES = Role.PARTICIPANT

# The gallery is curated: the people who run the site fill it, everybody else looks.
MANAGE_GALLERY = Role.ADMIN
EDIT_HOME_PAGE = Role.OWNER


def rank(user) -> int:
    """Where ``user`` stands in ``User.ROLE_HIERARCHY``: -1 for a visitor, or for whatever is not a
    member at all (an event's upload token stands for the event)."""
    if not getattr(user, "is_authenticated", False) or not hasattr(user, "get_role_rank"):
        return -1
    return user.get_role_rank()


def role_at_least(user, role: str) -> bool:
    """Whether ``user``'s role is ``role`` or above, a superuser or not."""
    return rank(user) >= User.ROLE_HIERARCHY.index(role)


def at_least(user, role: str) -> bool:
    """Whether ``user`` holds ``role`` or above; a superuser holds every role."""
    return bool(getattr(user, "is_superuser", False)) or role_at_least(user, role)


def can_assign_role(editor, role: str) -> bool:
    """Whether ``editor`` may give somebody ``role``: up to their own, from an organizer up. A
    participant comes with a confirmed address, so only an admin or above gives it by hand."""
    if role not in User.ROLE_HIERARCHY:
        return False
    if getattr(editor, "is_superuser", False):
        return True
    if not role_at_least(editor, Role.ORGANIZER):
        return False
    return role_at_least(editor, Role.ADMIN if role == Role.PARTICIPANT else role)


def role_change_refusal(editor, target, role: str) -> str:
    """Why ``editor`` may not give ``target`` (None for a new account) ``role``; empty when they may."""
    if target is not None and not can_manage_user(editor, target):
        return "You don't have permission to edit this user's role."
    if not can_assign_role(editor, role):
        return "You don't have permission to assign this role."
    return ""


def can_manage_user(editor, target) -> bool:
    """Whether ``editor`` may change ``target``'s account: anybody at or below their own role, from an
    organizer up."""
    if getattr(editor, "is_superuser", False):
        return True
    return role_at_least(editor, Role.ORGANIZER) and rank(editor) >= rank(target)
