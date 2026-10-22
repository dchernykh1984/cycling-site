"""Serialising schema.org data for a <script type="application/ld+json"> block.

The block is raw text to the browser: character references inside it are not decoded, so JSON that
went through django.utils.html.escape() reads as {&quot;@context&quot;: ...} to a search engine and
fails to parse -- the markup was there, and no engine could use it. What actually has to be kept out
is a "</script>" (or "<!--") in some title ending the block early; escaping <, > and & as JSON
unicode escapes does that and leaves the JSON valid, the same way Django's json_script does.
"""

import json

_ESCAPES = {ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026"}


def dumps(data) -> str:
    """``data`` as JSON that is safe to place inside a script element and still parses as JSON."""
    return json.dumps(data, ensure_ascii=False).translate(_ESCAPES)
