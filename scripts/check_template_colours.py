"""Pre-commit hook: no hex colour in the site's templates; colours come from the skin.

A template outside skins/ that writes #2c3e50 paints that colour in every skin, so a dark skin or a
designer's skin cannot change it and its contrast is checked in none of them. Colours belong to
the skin's variables (--bs-*, --skin-*), which every skin sets for itself.

Comments are left out before the scan -- "issue #118" is not a colour. The colours already in the
templates when the rule came in are listed in scripts/template_colours_allowed.txt as "path #hex";
the hook fails on any other, and on a listed one that is gone, so the list only ever shrinks.
"""

import pathlib
import re
import subprocess
import sys

ALLOWED = pathlib.Path(__file__).with_name("template_colours_allowed.txt")

COMMENTS = re.compile(
    r"\{% comment %\}.*?\{% endcomment %\}"  # Django block comments
    r"|\{#.*?#\}"  # Django line comments
    r"|<!--.*?-->"  # HTML
    r"|/\*.*?\*/"  # CSS and JS blocks
    r"|(?:(?<=\s)|^)//[^\n]*",  # JS line comments, not the // of a URL
    re.DOTALL | re.MULTILINE,
)
# 3, 4, 6 or 8 hex digits, but not a link to an anchor (href="#add", data-bs-target="#bad", a URL's
# /#abc, a template tag's {% url 'x' %}#add or {{ link }}#abc) or a character reference (&#123;).
HEX = re.compile(
    r"(?<!href=[\"'])(?<!target=[\"'])(?<!%\})(?<!\}\})(?<![&\w/])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"
)


def templates():
    """Every tracked template outside skins/: <app>/templates/**.html and templates/**.html."""
    git = ["git", "ls-files", "*.html"]
    listed = subprocess.run(git, capture_output=True, text=True, check=True)  # noqa: S603 -- fixed argv, no shell
    return [
        path
        for path in listed.stdout.split()
        if not path.startswith("skins/") and ("/templates/" in path or path.startswith("templates/"))
    ]


def colours(text):
    """The hex colours a template paints, comments left out, as written (case kept)."""
    return HEX.findall(COMMENTS.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text))


def found_in(paths):
    return {(path, colour.lower()) for path in paths for colour in colours(pathlib.Path(path).read_text("utf-8"))}


def allowed(listing):
    pairs = set()
    for line in listing.read_text("utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            path, colour = line.split()
            pairs.add((path, colour.lower()))
    return pairs


def main(paths=None, listing=ALLOWED):
    found = found_in(paths if paths is not None else templates())
    known = allowed(listing)
    new = sorted(found - known)
    gone = sorted(known - found)
    for path, colour in new:
        print(f"{path}: {colour} -- use a skin variable (var(--bs-...) or var(--skin-...)) instead")
    for path, colour in gone:
        print(f"{listing.name}: {path} {colour} is gone from the template; drop the line")
    return 1 if new or gone else 0


if __name__ == "__main__":
    sys.exit(main())
