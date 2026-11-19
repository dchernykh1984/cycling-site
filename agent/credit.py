"""The one line that credits an event to where it was announced, shared by the agents that add one.

The Telegram agent credits a proposed event to the channel it came from, in these words, so events
read the same however they arrived. What may be named in the label is the agent's own rule (see its
attribution module); the wording lives here.
"""

from __future__ import annotations

# The credit line, per locale. Russian is the wording the maintainer asked for; the other two say
# the same thing. None of them names a platform. Built from code points so this file stays ASCII
# like the rest of the source.
_CREDIT = {
    "ru": "".join(chr(c) for c in (0x418, 0x441, 0x442, 0x43E, 0x447, 0x43D, 0x438, 0x43A))  # Istochnik
    + " "
    + "".join(chr(c) for c in (0x43E, 0x431, 0x44A, 0x44F, 0x432, 0x43B, 0x435, 0x43D, 0x438, 0x44F)),  # obyavleniya
    "kk": "".join(chr(c) for c in (0x425, 0x430, 0x431, 0x430, 0x440, 0x43B, 0x430, 0x43D, 0x434, 0x44B, 0x440, 0x443))
    + " "
    + "".join(chr(c) for c in (0x43A, 0x4E9, 0x437, 0x456)),  # "Khabarlandyru kozi"
    "en": "Announcement source",
}


def with_credit(text: str, label: str, locale: str) -> str:
    """The description with the credit line appended, as its own paragraph."""
    credit = f"<p>{_CREDIT[locale]}: {label}</p>"
    return f"{text}\n{credit}" if text else credit
