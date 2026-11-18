"""Who may read an event's protocols: the one rule the protocol pages and the API both ask."""

from __future__ import annotations

from calendar_app.models import Competition
from calendar_app.visibility import can_see

from .models import Protocol


def shows_protocols(user, competition: Competition) -> bool:
    """Whether ``user`` may read this event's protocols: a published event's, which nobody hid.

    An invite-only event's results are as private as its page (issue #313): only for the people it lets
    in and those who manage it. A hidden event's are nobody's, its managers' included.
    """
    return (
        competition.status == Competition.Status.APPROVED
        and not competition.is_deleted
        and not competition.is_hidden
        and (not competition.invite_only or can_see(user, competition))
    )


def readable_protocol(user, pk: int) -> Protocol | None:
    """Protocol ``pk`` when ``user`` may read it; None for one they may not, as for one that does not exist."""
    protocol = Protocol.objects.select_related("competition__submitted_by").filter(pk=pk).first()
    if protocol is None or not shows_protocols(user, protocol.competition):
        return None
    return protocol
