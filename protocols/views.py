from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext
from django.views.decorators.clickjacking import xframe_options_sameorigin

from calendar_app.models import Competition
from calendar_app.visibility import can_see

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
    b"function l(){s();"
    b'window.parent.postMessage(Object.assign({type:"protocol-loaded"},__META__),"*");}'
    b'if(document.readyState==="loading"){'
    b'document.addEventListener("DOMContentLoaded",l);}else{l();}'
    # The page's script may start after this frame has already reported: it asks again.
    b'window.addEventListener("message",function(e){'
    b'if(e.source===window.parent&&e.data&&e.data.type==="protocol-measure")l();});'
    b"new MutationObserver(s).observe(document.documentElement,"
    b'{attributes:true,childList:true,subtree:true,attributeFilter:["style"]});'
    b"})();</script>"
)


def protocol_state(protocol: Protocol) -> dict:
    """What the reader is shown for a protocol, read off one row so the parts always agree.

    The live page trusts only the state that arrives *with* the content it applies: a newer upload
    can land between asking whether anything changed and fetching the content, and the content then
    belongs to that newer upload, not to the one the question was answered about.
    """
    return {"hash": protocol.file_hash, "is_live": protocol.is_live, "shown": "html"}


def _inject_resize_script(content: bytes, state: dict) -> bytes:
    # The frame tells its parent which upload it is, so the parent confirms what it actually shows.
    # A server error page carries no such script, which is how a failed reload is told apart.
    meta = json.dumps(state).replace("<", "\\u003c").encode()
    script = _RESIZE_SCRIPT.replace(b"__META__", meta)
    lower = content.lower()
    idx = lower.rfind(b"</body>")
    if idx != -1:
        return content[:idx] + script + content[idx:]
    return content + script


def image_sources(request) -> list[str]:
    """Where a protocol may load images from: this site, and wherever this site keeps its media.

    A protocol is a file somebody else wrote, shown on our domain, so it is framed with `sandbox`
    and given a policy that forbids it to reach outside. Forbidding *everything* outside also
    forbade the organizer's own logo, uploaded to this very site -- which is what this allows.

    The addresses are read off the request rather than written down: the same code runs on
    universalbicycle.team, on a staging host and on a developer's laptop, and each has to allow its
    own address and no other. Django has already checked that host against ALLOWED_HOSTS by the
    time a view runs, so it is the site's real address and not one a caller chose.

    `'self'` cannot do this job. The frame carries `sandbox` without `allow-same-origin`, so the
    protocol's own origin is opaque and `'self'` matches nothing at all -- the origin has to be
    named in full.
    """
    sources = [f"{request.scheme}://{request.get_host()}"]
    media = getattr(settings, "MEDIA_URL", "") or ""
    if "://" in media:
        # Media on a bucket or a CDN is a different origin from the site's own.
        parts = urlsplit(media)
        elsewhere = f"{parts.scheme}://{parts.netloc}"
        if elsewhere not in sources:
            sources.append(elsewhere)
    return sources


def content_security_policy(request) -> str:
    """The policy a protocol is served under: nothing but its own markup, and our own images."""
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'unsafe-inline'",
            "style-src 'unsafe-inline'",
            " ".join(["img-src data:", *image_sources(request)]),
            "connect-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "sandbox allow-scripts",
        ]
    )


def _published_protocol(request, pk) -> Protocol:
    """A protocol of a published event, or 404 -- including for an invite-only event the reader
    has not been let into, whose results are as private as its page (issue #313)."""
    protocol = get_object_or_404(
        Protocol.objects.select_related("competition__submitted_by"),
        pk=pk,
        competition__status=Competition.Status.APPROVED,
        competition__is_hidden=False,
        competition__is_deleted=False,
    )
    if protocol.competition.invite_only and not can_see(request.user, protocol.competition):
        raise Http404
    return protocol


def protocol_last_updated(request, pk):
    protocol = _published_protocol(request, pk)
    return JsonResponse(
        {
            "last_updated": protocol.last_updated.isoformat(),
            "file_hash": protocol.file_hash,
            "is_live": protocol.is_live,
            "shown": protocol_state(protocol)["shown"],
        }
    )


@xframe_options_sameorigin
def protocol_html(request, pk):
    protocol = _published_protocol(request, pk)
    if not protocol.html_file:
        raise Http404
    try:
        content = protocol.html_file.read()
    except OSError:
        raise Http404 from None
    content = _sanitize_protocol_html(content)
    content = _inject_resize_script(content, protocol_state(protocol))
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = content_security_policy(request)
    response["Cache-Control"] = "no-store"
    return response


def protocol_detail(request, pk):
    protocol = _published_protocol(request, pk)
    versions = protocol.versions.all()[:_MAX_VERSIONS]
    kind = gettext("Absolute results") if protocol.protocol_type == "absolute" else gettext("Group results")
    return render(
        request,
        "protocols/detail.html",
        {
            "protocol": protocol,
            "versions": versions,
            "state": protocol_state(protocol),
            # Without it a link to the protocol pasted into a chat previews with an empty title.
            "meta_title": f"{protocol.competition.title} \u2014 {kind}",
            "poll_interval_ms": settings.PROTOCOL_POLL_INTERVAL_MS,
            "load_timeout_ms": settings.PROTOCOL_LOAD_TIMEOUT_MS,
        },
    )
