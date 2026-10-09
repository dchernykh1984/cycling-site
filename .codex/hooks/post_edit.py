#!/usr/bin/env python3
"""Tidy and check the files an agent just edited, before the commit gate does.

Two things, mirroring what this repository already enforces elsewhere. It runs
``ruff format`` on an edited Python file, which is what the Claude hook in
``.claude/settings.json`` does. And it reports non-ASCII bytes, which is what the
pre-commit gate rejects -- the patterns live in ``checks.json`` beside this file and
are kept the same as the ones in ``.pre-commit-config.yaml``.

Reporting, not undoing: a post-edit hook sees the file after it was written. Saying so
at the moment of the edit is worth a lot more than finding out at commit time, which is
when a UTF-16 redirect usually surfaces -- the text looks plain in an editor and only
the bytes are wrong.

Codex writes through ``apply_patch``, which carries its paths inside the patch body
rather than in a ``file_path`` field, and one patch may touch several files. Both
shapes are read here, so the hook fires for Codex and for a plain editor tool alike.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Move to): ([^\r\n]+)\r?$", re.MULTILINE)


def edited_paths(payload: dict[str, Any], root: Path) -> list[Path]:
    """Every file this edit touched, resolved and kept inside the repository."""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return []
    raw_paths: list[str] = []
    raw_path = tool_input.get("file_path")
    if isinstance(raw_path, str):
        raw_paths.append(raw_path)
    command = tool_input.get("command")
    if isinstance(command, str):
        raw_paths.extend(PATCH_PATH.findall(command))
    cwd = Path(payload.get("cwd") or root).resolve()
    paths: list[Path] = []
    for name in raw_paths:
        path = (cwd / name).resolve()
        if path.is_relative_to(root) and path.is_file() and path not in paths:
            paths.append(path)
    return paths


def _selected(paths: list[Path], root: Path, pattern: str, exclude: str = "") -> list[Path]:
    chosen = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not re.search(pattern, relative):
            continue
        if exclude and re.search(exclude, relative):
            continue
        chosen.append(path)
    return chosen


def reformat(paths: list[Path], root: Path, checks: dict[str, str]) -> None:
    """Run ruff over the edited Python files, preferring the project's own copy."""
    targets = _selected(paths, root, checks["format"])
    if not targets:
        return
    ruff = root / ".venv/bin/ruff"
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, paths resolved inside the repo
        [str(ruff) if ruff.exists() else "ruff", "format", "--quiet", *map(str, targets)],
        check=False,
    )


def violations(paths: list[Path], root: Path, checks: dict[str, str]) -> list[str]:
    """The edited files carrying a byte the pre-commit ASCII gate would reject."""
    return [
        path.relative_to(root).as_posix()
        for path in _selected(paths, root, checks["files"], checks["exclude"])
        if any(byte > 127 for byte in path.read_bytes())
    ]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    checks = json.loads((ROOT / ".codex/hooks/checks.json").read_text(encoding="utf-8"))
    paths = edited_paths(payload, ROOT)
    reformat(paths, ROOT, checks)
    problems = violations(paths, ROOT, checks)
    if not problems:
        return 0
    print(
        "Non-ASCII bytes in " + ", ".join(problems) + ". Fix before committing.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
