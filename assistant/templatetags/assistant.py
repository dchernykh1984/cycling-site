"""``{% assistant_chat %}``: the assistant's chat on the pages where an event or a news item is written (#353).

Offered on an event's pages to organizers and up, on a news item's to admins and up, and only when
the site has the model's key. The page carries the conversation so far -- the subject's own on its
edit page, or the one a refused form posted back, when it is the reader's -- and what the chat reads
and fills in the form of its kind.
"""

from django import template
from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from assistant.conversations import may_see, offered, subject_field
from assistant.models import Conversation

register = template.Library()

_LANGUAGES = ("ru", "kk", "en")
# What the chat reads off each kind's form and fills in: plain fields by name, and the editors of its
# rich texts by the id of the box each one's Quill lives in.
_FORMS = {
    "event": {
        "fields": [
            *(f"{name}_{lang}" for name in ("title", "preview_text") for lang in _LANGUAGES),
            "date_start",
            "date_end",
            "url_announcement",
            "url_registration",
            "url_route",
            "url_regulations",
            "url_results",
            "location",
            "new_venue_city",
        ],
        "editors": {f"description_{lang}": f"quill-desc-{lang}" for lang in _LANGUAGES},
        "attach": True,
    },
    "news": {
        "fields": [f"{name}_{lang}" for name in ("title", "intro") for lang in _LANGUAGES],
        "editors": {f"body_{lang}": f"quill-{lang}" for lang in _LANGUAGES},
        "attach": False,
    },
}


def _conversation(request, subject, kind: str) -> Conversation | None:
    if subject is not None:
        field, _kind = subject_field(subject)
        return Conversation.objects.filter(**{field: subject}).first()
    posted = request.POST.get("assistant_conversation", "") if request.method == "POST" else ""
    if not posted.isdigit():
        return None
    unlinked = Conversation.objects.filter(competition__isnull=True, news__isnull=True)
    conversation = unlinked.filter(pk=int(posted), kind=kind).first()
    return conversation if conversation is not None and may_see(request.user, conversation) else None


def _first_question(kind: str, editing: bool) -> str:
    if kind == Conversation.Kind.NEWS:
        return (
            _("What would you like to change in this news item?")
            if editing
            else _("What news would you like to write?")
        )
    return _("What would you like to change in this event?") if editing else _("What event would you like to add?")


@register.inclusion_tag("assistant/_chat.html", takes_context=True)
def assistant_chat(context, kind: str = "event"):
    request = context.get("request")
    user = getattr(request, "user", None)
    if not settings.ASSISTANT_LLM_API_KEY or user is None or not offered(user, kind):
        return {"offered": False}
    subject = context.get("article" if kind == Conversation.Kind.NEWS else "competition")
    conversation = _conversation(request, subject, kind)
    first = _first_question(kind, subject is not None)
    return {
        "offered": True,
        "history": [{"role": m.role, "text": m.text} for m in conversation.messages.all()] if conversation else [],
        "config": {
            "kind": kind,
            **_FORMS[kind],
            "conversationId": conversation.pk if conversation else None,
            "subjectId": subject.pk if subject else None,
            "start": reverse("api_v1:start_conversation"),
            "trackStart": reverse("api_v1:track_start"),
            "language": (get_language() or "ru").split("-")[0],
            "words": {
                "first": first,
                "thinking": _("The assistant is writing..."),
                "failed": _("The message did not go through. Send it again."),
                "attachedRoute": _("Attached to the form as the route: %(name)s"),
                "attachedRegulations": _("Attached to the form as the regulations: %(name)s"),
                "wrongFile": _("Attach a GPX or KML track, or the regulations as a PDF."),
            },
        },
    }
