from __future__ import annotations

import hashlib
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import get_valid_filename
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt

from calendar_app.models import Competition

from .models import Protocol, ProtocolVersion

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


@csrf_exempt
def upload_protocol(request):  # noqa: C901
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    upload_token = request.POST.get("upload_token", "")
    if not upload_token:
        return JsonResponse({"error": "upload_token is required"}, status=400)

    try:
        competition = Competition.objects.get(
            upload_token=upload_token,
            status=Competition.Status.APPROVED,
        )
    except (Competition.DoesNotExist, ValidationError):
        return JsonResponse({"error": "Invalid upload token"}, status=401)

    protocol_type = request.POST.get("protocol_type", "absolute")
    if protocol_type not in ("absolute", "group"):
        return JsonResponse({"error": "Invalid protocol_type"}, status=400)

    is_live_str = request.POST.get("is_live", "true").lower()
    if is_live_str in ("true", "1", "yes"):
        is_live = True
    elif is_live_str in ("false", "0", "no"):
        is_live = False
    else:
        return JsonResponse({"error": "Invalid is_live value"}, status=400)
    stage_label = request.POST.get("stage_label", "")

    if "html_file" not in request.FILES:
        return JsonResponse({"error": "html_file is required"}, status=400)

    uploaded = request.FILES["html_file"]

    content_type = getattr(uploaded, "content_type", "") or ""
    media_type = content_type.split(";")[0].strip()
    if media_type != "text/html":
        return JsonResponse({"error": "File must be text/html"}, status=400)

    # Validate file extension server-side (client-provided Content-Type can be spoofed).
    raw_name = uploaded.name or ""
    if not raw_name.lower().endswith((".html", ".htm")):
        return JsonResponse({"error": "File must have .html or .htm extension"}, status=400)

    max_mb = getattr(settings, "MAX_PROTOCOL_SIZE_MB", 5)
    if uploaded.size > max_mb * 1024 * 1024:
        return JsonResponse({"error": f"File too large (max {max_mb} MB)"}, status=400)

    content = uploaded.read()

    # Verify that the file content begins with an HTML marker as a basic integrity check.
    # Strip leading whitespace then the UTF-8 BOM (if present) then any further whitespace.
    _c = content.lstrip()
    if _c.startswith(b"\xef\xbb\xbf"):
        _c = _c[3:]
    content_start = _c.lstrip()[:15].lower()
    if not content_start.startswith(b"<"):
        return JsonResponse({"error": "File does not appear to be valid HTML"}, status=400)

    file_hash = hashlib.sha256(content).hexdigest()
    filename = get_valid_filename(uploaded.name) or "protocol.html"
    # Ensure stored filename always ends with .html regardless of the upload name.
    if not filename.lower().endswith(".html"):
        filename = filename + ".html"

    protocol, _ = Protocol.objects.get_or_create(
        competition=competition,
        protocol_type=protocol_type,
    )

    if protocol.html_file:
        protocol.html_file.delete(save=False)

    protocol.is_live = is_live
    protocol.stage_label = stage_label
    protocol.file_hash = file_hash
    protocol.html_file.save(filename, ContentFile(content), save=False)
    protocol.save()

    version = ProtocolVersion(protocol=protocol, file_hash=file_hash)
    version.html_file.save(f"v_{filename}", ContentFile(content), save=True)

    old_ids = list(
        ProtocolVersion.objects.filter(protocol=protocol)
        .order_by("-saved_at")
        .values_list("pk", flat=True)[_MAX_VERSIONS:]
    )
    if old_ids:
        for old in ProtocolVersion.objects.filter(pk__in=old_ids):
            old.html_file.delete(save=False)
        ProtocolVersion.objects.filter(pk__in=old_ids).delete()

    return JsonResponse({"id": protocol.pk, "file_hash": file_hash})


def protocol_last_updated(request, pk):
    protocol = get_object_or_404(Protocol, pk=pk, competition__status=Competition.Status.APPROVED)
    return JsonResponse(
        {
            "last_updated": protocol.last_updated.isoformat(),
            "file_hash": protocol.file_hash,
            "is_live": protocol.is_live,
        }
    )


@xframe_options_sameorigin
def protocol_html(request, pk):
    protocol = get_object_or_404(Protocol, pk=pk, competition__status=Competition.Status.APPROVED)
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
    protocol = get_object_or_404(Protocol, pk=pk, competition__status=Competition.Status.APPROVED)
    versions = protocol.versions.all()[:_MAX_VERSIONS]
    return render(
        request,
        "protocols/detail.html",
        {
            "protocol": protocol,
            "versions": versions,
        },
    )
