"""Read instagram_accounts.yaml into the accounts a run should visit (no I/O, unit-tested)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

# A username as Instagram allows it: letters, digits, dots and underscores. Entries are written by
# hand, so a pasted profile URL is accepted too and reduced to the name it points at.
_USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_PROFILE_URL = re.compile(r"instagram\.com/([A-Za-z0-9._]{1,30})")


@dataclass(frozen=True)
class Account:
    """One Instagram account to read, with what the maintainers know about it."""

    username: str
    hint: str = ""  # free-text nudge passed to the model, like a web source's hint
    city: str = ""  # where this club rides, for posts that never name the place


def _username_of(value: str) -> str:
    """The account name from a bare handle, an @handle or a pasted profile URL; "" if unusable."""
    text = (value or "").strip().strip("/")
    if not text:
        return ""
    url = _PROFILE_URL.search(text)
    if url:
        return url.group(1)
    text = text.removeprefix("@")
    # A query string on a pasted link ("?igsh=...") survives the URL match above only when the link
    # had no host, so drop anything after the name itself.
    text = text.split("?", 1)[0].split("/", 1)[0]
    return text if _USERNAME.match(text) else ""


def enabled_usernames(text: str) -> list[str]:
    """The names a workflow needs to give each account a job of its own."""
    return [account.username for account in parse_accounts(text)]


def parse_accounts(text: str) -> list[Account]:
    """The enabled accounts declared in the instagram_accounts.yaml text, de-duplicated in order."""
    data = yaml.safe_load(text)
    entries = data.get("accounts") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    accounts: list[Account] = []
    seen: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            username, hint, city, enabled = _username_of(entry), "", "", True
        elif isinstance(entry, dict):
            username = _username_of(str(entry.get("username") or entry.get("url") or ""))
            hint = str(entry.get("hint") or "").strip()
            city = str(entry.get("city") or "").strip()
            enabled = bool(entry.get("enabled", True))
        else:
            continue
        if not username or not enabled or username.lower() in seen:
            continue
        seen.add(username.lower())
        accounts.append(Account(username=username, hint=hint, city=city))
    return accounts


def main() -> None:
    """`python -m instagram_agent.accounts` prints the enabled accounts as a JSON array.

    The workflow reads it to build one job per account: keeping the list in the workflow as well
    would mean two places to edit and one of them silently going stale.
    """
    import json
    import sys
    from pathlib import Path

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("instagram_accounts.yaml")
    print(json.dumps(enabled_usernames(path.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
