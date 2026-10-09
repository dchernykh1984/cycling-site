"""The Codex post-edit hook, which pytest would never find where it lives.

`.codex/` starts with a dot, so pytest does not recurse into it; the hook's test has to
sit here or it does not run at all. What is worth protecting is the path extraction:
Codex writes through `apply_patch`, which names its files inside the patch body rather
than in a `file_path` field, so a hook that only reads `file_path` silently does nothing
for the agent it was written for -- which is exactly how this one shipped at first.
"""

import importlib.util
import json
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
HOOK = ROOT / ".codex" / "hooks" / "post_edit.py"


def _module():
    spec = importlib.util.spec_from_file_location("codex_post_edit", HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook():
    return _module()


@pytest.fixture
def checks():
    return json.loads((ROOT / ".codex" / "hooks" / "checks.json").read_text(encoding="utf-8"))


def _patch(*names: str) -> dict:
    body = "*** Begin Patch\n" + "".join(f"*** Update File: {n}\n" for n in names) + "*** End Patch"
    return {"tool_input": {"command": body}, "cwd": str(ROOT)}


class TestEditedPaths:
    def test_a_patch_naming_several_files_yields_all_of_them(self, hook):
        found = hook.edited_paths(_patch("manage.py", "pyproject.toml"), ROOT)
        assert [p.name for p in found] == ["manage.py", "pyproject.toml"]

    def test_a_plain_file_path_is_read_too(self, hook):
        payload = {"tool_input": {"file_path": "manage.py"}, "cwd": str(ROOT)}
        assert [p.name for p in hook.edited_paths(payload, ROOT)] == ["manage.py"]

    def test_a_path_outside_the_repository_is_refused(self, hook):
        payload = {"tool_input": {"file_path": "/etc/hosts"}, "cwd": str(ROOT)}
        assert hook.edited_paths(payload, ROOT) == []

    def test_a_file_that_does_not_exist_is_skipped(self, hook):
        assert hook.edited_paths(_patch("no/such/file.py"), ROOT) == []

    def test_a_payload_without_an_edit_yields_nothing(self, hook):
        assert hook.edited_paths({}, ROOT) == []


class TestViolations:
    def test_non_ascii_in_a_checked_file_is_reported(self, hook, checks):
        path = ROOT / "manage_non_ascii_probe.py"
        # Built from its code point: a literal em dash here would trip the ASCII
        # gate on this very file.
        path.write_text("x = 1  # " + chr(0x2014) + "\n", encoding="utf-8")
        try:
            assert hook.violations([path], ROOT, checks) == ["manage_non_ascii_probe.py"]
        finally:
            path.unlink()

    def test_an_ascii_file_passes(self, hook, checks):
        assert hook.violations([ROOT / "manage.py"], ROOT, checks) == []

    def test_a_translation_catalogue_is_not_checked(self, hook, checks):
        """Catalogues are where the Russian lives; the pre-commit gate exempts them too."""
        catalogue = ROOT / "cycling_site" / "locale" / "ru" / "LC_MESSAGES" / "django.po"
        assert hook.violations([catalogue], ROOT, checks) == []

    def test_the_exempt_guidance_files_are_not_checked(self, hook, checks):
        guidance = ROOT / "agent" / "guidance.md"
        assert hook.violations([guidance], ROOT, checks) == []


def test_the_checks_match_the_pre_commit_gate(checks):
    """One list of exemptions, in two files; a drift between them is the bug this catches."""
    import re

    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    exclude = re.search(r"exclude: (\^\(uv\\\.lock\|[^\n]+)", config)
    assert exclude, "the ASCII hook's exclude pattern moved"
    assert checks["exclude"] == exclude.group(1).strip()
