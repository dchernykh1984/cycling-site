"""Every ``<object>.<Choices>.<MEMBER>`` a template compares with exists on that object's model.

Django's ``{% if %}`` reads a name that does not resolve as false, so ``competition.Status.APROVED``
would hide a banner without a word. A template object is known by the name it has in the template
(``MODELS``); one that is not listed there fails the test until it is.
"""

import os
import re
from pathlib import Path

from django.db import models

from calendar_app.models import Competition
from knowledge.models import DraftSubmission
from protocols.models import Protocol
from trainer.models import VirtualRide

ROOT = Path(__file__).resolve().parent.parent
SKIPPED = {".git", ".venv", "node_modules", "tmp", "staticfiles", "__pycache__", "media"}
MODELS = {
    "comp": Competition,
    "competition": Competition,
    "protocol": Protocol,
    "ride": VirtualRide,
    "sub": DraftSubmission,
    "submission": DraftSubmission,
}
# The name just before the choices: ``protocol.competition.Status.APPROVED`` is read as ``competition``.
REFERENCE = re.compile(r"\b(\w+)\.([A-Z]\w*)\.([A-Z][A-Z0-9_]*)\b")


def _missing(text: str) -> list[str]:
    missing = []
    for name, choices, member in REFERENCE.findall(text):
        if name == "ROLES":  # tests/test_roles.py
            continue
        found = getattr(MODELS.get(name), choices, None)
        if not (isinstance(found, type) and issubclass(found, models.Choices) and member in found.names):
            missing.append(f"{name}.{choices}.{member}")
    return missing


def test_every_choice_a_template_names_exists():
    missing = []
    for folder, subfolders, files in os.walk(ROOT):
        subfolders[:] = [name for name in subfolders if name not in SKIPPED]
        for name in files:
            if name.endswith(".html"):
                path = Path(folder) / name
                missing += [f"{path.relative_to(ROOT)}: {ref}" for ref in _missing(path.read_text(encoding="utf-8"))]
    assert missing == []


def test_a_mistyped_choice_is_found():
    assert _missing("{% if protocol.competition.status == protocol.competition.Status.APROVED %}") == [
        "competition.Status.APROVED"
    ]
    assert _missing("{% if item.state == item.State.ACTIVE %}") == ["item.State.ACTIVE"]
    assert _missing("{% if ride.power_source == ride.PowerSource.DEMO %}{{ ROLES.Role.ADMIN }}") == []
