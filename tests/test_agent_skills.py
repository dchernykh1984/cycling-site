"""The project's skills are kept twice: for Claude Code in `.claude/skills` and for Codex in
`.agents/skills`. An edit made to one copy alone leaves the other agent working by the old rules -- it
happened to the translations skill (#384). Spec Kit's skills are generated for each agent and are left
out; the two copies of ours may differ only where each names its own agent.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE, CODEX = ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"


def _skills(folder):
    return {path.name for path in folder.iterdir() if path.is_dir() and not path.name.startswith("speckit-")}


def _files(folder):
    return sorted(path.relative_to(folder) for path in folder.rglob("*") if path.is_file())


def test_both_agents_have_the_same_skills():
    assert _skills(CLAUDE) == _skills(CODEX)


@pytest.mark.parametrize("name", sorted(_skills(CLAUDE)))
def test_a_skill_tells_both_agents_the_same(name):
    assert _files(CLAUDE / name) == _files(CODEX / name)
    for relative in _files(CLAUDE / name):
        claude = (CLAUDE / name / relative).read_text(encoding="utf-8")
        codex = (CODEX / name / relative).read_text(encoding="utf-8").replace("Codex", "Claude")
        assert codex == claude, f"{name}/{relative}"
