"""Guard against multi-line ``{# ... #}`` Django template comments.

Django only strips ``{# ... #}`` comments that open and close on the *same* line -- its
tokenizer regex (``{#.*?#}``) runs without ``re.DOTALL``. A comment split across two lines is
therefore not recognised as a comment and renders as literal text on the page (issue #233 shipped
two of these, leaking developer notes onto every event page). Multi-line comments must use
``{% comment %} ... {% endcomment %}`` instead. This test fails on any ``{# ... #}`` whose closing
delimiter is not on the same line, across every project template.
"""

import pathlib

import pytest

# Repo root == parent of this tests/ directory. Walking from here keeps the scan to our own
# templates and never reaches the virtualenv's vendored packages.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SKIP_DIRS = {".venv", "venv", "node_modules", "staticfiles", "__pycache__", ".git", "media"}


def _iter_templates():
    for path in _REPO_ROOT.rglob("*.html"):
        if _SKIP_DIRS.isdisjoint(path.parts):
            yield path


def _multiline_comments(text: str) -> list[int]:
    """Return the 1-based line numbers of any ``{#`` whose ``#}`` is not on the same line."""
    offending = []
    idx = 0
    while (start := text.find("{#", idx)) != -1:
        close = text.find("#}", start)
        if close == -1 or "\n" in text[start:close]:
            offending.append(text.count("\n", 0, start) + 1)
        idx = close + 2 if close != -1 else start + 2
    return offending


def test_no_multiline_django_template_comments():
    violations = []
    for path in _iter_templates():
        for line in _multiline_comments(path.read_text(encoding="utf-8")):
            violations.append(f"{path.relative_to(_REPO_ROOT)}:{line}")
    assert not violations, (
        "Multi-line {# ... #} comments render as literal text (Django only strips single-line "
        "ones). Use {% comment %} ... {% endcomment %} instead. Offending sites:\n  " + "\n  ".join(violations)
    )


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("{# single line #}", 0),
        ("{# opens here\n   closes there #}", 1),
        ("prefix\n{# bad\ncomment #}", 1),
        ("{# a #}{# b #}", 0),
        ("{# never closed", 1),
    ],
)
def test_multiline_comment_detector(snippet, expected):
    """The detector itself: single-line and paired comments pass; split/unclosed ones are flagged."""
    assert len(_multiline_comments(snippet)) == expected
