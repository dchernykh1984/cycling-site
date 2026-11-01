"""Credit a proposed event to where it was announced, without disclosing how to get there.

A public group is credited by its handle -- "tg: @almatyriders" -- which anyone may search for. A
private channel is credited by its display name alone ("Velosreda s Alatau Racing"), the way a
member would say it aloud: no link, no invite, no id, because the name invites nobody in while an
invite hash does. The wording of the credit line is the one the Instagram agent already publishes,
so events read the same however they arrived.

The name of a private channel is not in the channels file (the file carries bare ids on purpose);
it is read from Telegram itself when the channel is opened, and threaded to here.
"""

from __future__ import annotations

import re
from dataclasses import replace

from agent.credit import with_credit
from agent.models import Candidate

# Any t.me address, bare or with a scheme. Shared with run._scrubbed: one definition of what may
# never reach a published event or a credit line.
TME_LINK = re.compile(r"(?:https?://)?(?:www\.)?t(?:elegram)?\.me/\S+", re.IGNORECASE)


def source_label(ref: str, title: str) -> str:
    """How the event names where it came from: a searchable handle, or a bare display name.

    Empty when there is nothing safe to say -- a private channel whose title Telegram did not give
    is credited as nothing rather than as its invite or id.
    """
    if ref.startswith("@"):
        return f"tg: {ref}"
    return TME_LINK.sub("", title or "").strip()


def credit_source(candidate: Candidate, label: str) -> Candidate:
    """The candidate with the one allowed source line appended to every locale's description."""
    if not label:
        return candidate
    return replace(
        candidate,
        description=with_credit(candidate.description, label, "ru"),
        description_kk=with_credit(candidate.description_kk, label, "kk"),
        description_en=with_credit(candidate.description_en, label, "en"),
    )
