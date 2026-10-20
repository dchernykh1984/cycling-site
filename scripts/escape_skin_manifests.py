"""Pre-commit hook: rewrite a skin's manifest.json with its non-ASCII text as \\uXXXX escapes.

A designer writes the skin's names in Russian and Kazakh as they read; the repository keeps every
json file ASCII. The hook rewrites the file and fails once, as a formatter does, so the second
commit goes through with the escaped text. JSON reads the escapes back as the same letters.
"""

import json
import pathlib
import sys


def main(paths):
    changed = False
    for path in map(pathlib.Path, paths):
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            print(f"{path}: not valid JSON: {error}")
            changed = True
            continue
        escaped = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
        if escaped != text:
            path.write_text(escaped, encoding="utf-8")
            print(f"{path}: rewritten with escaped text")
            changed = True
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
