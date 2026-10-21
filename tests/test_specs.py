"""The specifications (issue #337) stay in the shape the agents and people rely on, and point at
code that exists -- so a rename shows up here instead of leaving a spec quietly wrong."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "specs" / "site"
SITE_SPECS = sorted(SITE.glob("*.md"))
REQUIRED = (
    "**Status**:",
    "**Verified against**:",
    "**Code**:",
    "**Tests**:",
    "## Overview",
    "## User Scenarios",
    "## Functional Requirements",
    "## Key Entities",
    "## Local assumptions",
    "## Open Questions",
)
# A backticked repository path in the header lines: has a slash and a file or folder name; one
# starting with a slash is a URL the site serves, not a file.
PATH = re.compile(r"`([A-Za-z0-9_.-][A-Za-z0-9_./-]*/[A-Za-z0-9_.-]*)`")


def _header(text: str) -> str:
    """The lines before the overview, where a spec names its code and tests."""
    return text.split("## Overview", 1)[0]


def test_there_is_a_baseline():
    assert len(SITE_SPECS) >= 10


@pytest.mark.parametrize("spec", SITE_SPECS, ids=lambda p: p.name)
def test_every_baseline_spec_has_its_sections(spec):
    text = spec.read_text()
    missing = [heading for heading in REQUIRED if heading not in text]
    assert not missing, f"{spec.name} lacks {missing}"


@pytest.mark.parametrize("spec", SITE_SPECS, ids=lambda p: p.name)
def test_every_path_a_spec_names_exists(spec):
    named = PATH.findall(_header(spec.read_text()))
    assert named, f"{spec.name} names no code or tests"
    gone = [path for path in named if not (ROOT / path.rstrip("/")).exists()]
    assert not gone, f"{spec.name} names paths that no longer exist: {gone}"


@pytest.mark.parametrize("spec", SITE_SPECS, ids=lambda p: p.name)
def test_every_test_file_a_spec_names_by_itself_exists(spec):
    """A list of test files names the folder once and the rest bare: those must exist under tests/."""
    bare = set(re.findall(r"`(test_[a-z0-9_]+\.py)`", _header(spec.read_text())))
    present = {path.name for path in (ROOT / "tests").rglob("test_*.py")}
    assert not bare - present, f"{spec.name} names test files that do not exist: {sorted(bare - present)}"


def test_the_guide_lists_every_baseline_spec_and_nothing_else():
    guide = (ROOT / "specs" / "README.md").read_text()
    tree = guide.split("site/", 1)[1].split("<issue>", 1)[0]
    listed = set(re.findall(r"[a-z-]+\.md", tree))
    assert listed == {spec.name for spec in SITE_SPECS}


def test_every_feature_folder_starts_with_a_spec():
    for folder in (ROOT / "specs").iterdir():
        if folder.is_dir() and re.match(r"\d+-", folder.name):
            assert (folder / "spec.md").is_file(), f"{folder.name} has no spec.md"


def test_the_constitution_has_no_template_placeholders_left():
    text = (ROOT / ".specify" / "memory" / "constitution.md").read_text()
    assert not re.search(r"\[[A-Z][A-Z0-9_]+\]", text)
    assert "**Version**: " in text
