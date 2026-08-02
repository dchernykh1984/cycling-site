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

from agent.models import Candidate

# Any t.me address, bare or with a scheme. Shared with run._scrubbed: one definition of what may
# never reach a published event or a credit line.
TME_LINK = re.compile(r"(?:https?://)?(?:www\.)?t(?:elegram)?\.me/\S+", re.IGNORECASE)

# The credit line, per locale -- the same wording the Instagram agent publishes, built from code
# points so this file stays ASCII like the rest of the source.
_CREDIT = {
    "ru": "".join(chr(c) for c in (0x418, 0x441, 0x442, 0x43E, 0x447, 0x43D, 0x438, 0x43A))  # Istochnik
    + " "
    + "".join(chr(c) for c in (0x43E, 0x431, 0x44A, 0x44F, 0x432, 0x43B, 0x435, 0x43D, 0x438, 0x44F)),  # obyavleniya
    "kk": "".join(chr(c) for c in (0x425, 0x430, 0x431, 0x430, 0x440, 0x43B, 0x430, 0x43D, 0x434, 0x44B, 0x440, 0x443))
    + " "
    + "".join(chr(c) for c in (0x43A, 0x4E9, 0x437, 0x456)),  # "Khabarlandyru kozi"
    "en": "Announcement source",
}


def source_label(ref: str, title: str) -> str:
    """How the event names where it came from: a searchable handle, or a bare display name.

    Empty when there is nothing safe to say -- a private channel whose title Telegram did not give
    is credited as nothing rather than as its invite or id.
    """
    if ref.startswith("@"):
        return f"tg: {ref}"
    return TME_LINK.sub("", title or "").strip()


def _with_credit(text: str, label: str, locale: str) -> str:
    """The description with the credit line appended, as its own paragraph."""
    credit = f"<p>{_CREDIT[locale]}: {label}</p>"
    return f"{text}\n{credit}" if text else credit


def credit_source(candidate: Candidate, label: str) -> Candidate:
    """The candidate with the one allowed source line appended to every locale's description."""
    if not label:
        return candidate
    return replace(
        candidate,
        description=_with_credit(candidate.description, label, "ru"),
        description_kk=_with_credit(candidate.description_kk, label, "kk"),
        description_en=_with_credit(candidate.description_en, label, "en"),
    )
