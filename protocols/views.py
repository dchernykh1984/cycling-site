from __future__ import annotations

import re

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from calendar_app.models import Competition

from .models import Protocol

_MAX_VERSIONS = 10

# Strip elements that could redirect or load external code.
# CSP (default-src 'none') already blocks most attack vectors; these regexes
# are defense-in-depth for <script src=...>, <base>, and meta-refresh.
_EXT_SCRIPT_RE = re.compile(
    rb"<script\b[^>]*\bsrc\s*=[^>]*>.*?</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_BASE_TAG_RE = re.compile(rb"<base\b[^>]*/?>", re.IGNORECASE)
_META_REFRESH_RE = re.compile(
    rb'<meta\b(?=[^>]*\bhttp-equiv\s*=\s*["\']?refresh)[^>]*/?>',
    re.IGNORECASE,
)


def _sanitize_protocol_html(content: bytes) -> bytes:
    content = _EXT_SCRIPT_RE.sub(b"", content)
    content = _BASE_TAG_RE.sub(b"", content)
    content = _META_REFRESH_RE.sub(b"", content)
    return content


_RESIZE_SCRIPT = (
    b"<script>(function(){"
    b"function s(){"
    b'window.parent.postMessage({type:"protocol-resize",'
    b"h:document.documentElement.scrollHeight,"
    b'w:document.documentElement.scrollWidth},"*");}'
    b'if(document.readyState==="loading"){'
    b'document.addEventListener("DOMContentLoaded",s);}else{s();}'
    b"new MutationObserver(s).observe(document.documentElement,"
    b'{attributes:true,childList:true,subtree:true,attributeFilter:["style"]});'
    b"})();</script>"
)


def _inject_resize_script(content: bytes) -> bytes:
    lower = content.lower()
    idx = lower.rfind(b"</body>")
    if idx != -1:
        return content[:idx] + _RESIZE_SCRIPT + content[idx:]
    return content + _RESIZE_SCRIPT


def protocol_last_updated(request, pk):
    protocol = get_object_or_404(
        Protocol,
        pk=pk,
        competition__status=Competition.Status.APPROVED,
        competition__is_hidden=False,
        competition__is_deleted=False,
    )
    return JsonResponse(
        {
            "last_updated": protocol.last_updated.isoformat(),
            "file_hash": protocol.file_hash,
            "is_live": protocol.is_live,
        }
    )


@xframe_options_sameorigin
def protocol_html(request, pk):
    protocol = get_object_or_404(
        Protocol,
        pk=pk,
        competition__status=Competition.Status.APPROVED,
        competition__is_hidden=False,
        competition__is_deleted=False,
    )
    if not protocol.html_file:
        raise Http404
    try:
        content = protocol.html_file.read()
    except OSError:
        raise Http404 from None
    content = _sanitize_protocol_html(content)
    content = _inject_resize_script(content)
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; "
        "img-src data:; "
        "connect-src 'none'; "
        "object-src 'none'; "
        "frame-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "sandbox allow-scripts"
    )
    response["Cache-Control"] = "no-store"
    return response


def protocol_detail(request, pk):
    protocol = get_object_or_404(
        Protocol,
        pk=pk,
        competition__status=Competition.Status.APPROVED,
        competition__is_hidden=False,
        competition__is_deleted=False,
    )
    versions = protocol.versions.all()[:_MAX_VERSIONS]
    return render(
        request,
        "protocols/detail.html",
        {
            "protocol": protocol,
            "versions": versions,
        },
    )
