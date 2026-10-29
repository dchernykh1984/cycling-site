"""``{% assistant_chat %}``: the event assistant's chat on the pages where an event is added and edited (#353).

Offered to admins and the owner, and only when the site has the model's key. The page carries the
conversation so far -- the event's own on its edit page, or the one a refused form posted back.
"""

from django import template
from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from api.auth import is_admin
from assistant.models import Conversation

register = template.Library()


def _conversation(request, competition) -> Conversation | None:
    if competition is not None:
        return Conversation.objects.filter(competition=competition).first()
    posted = request.POST.get("assistant_conversation", "") if request.method == "POST" else ""
    if not posted.isdigit():
        return None
    return Conversation.objects.filter(pk=int(posted), competition__isnull=True).first()


@register.inclusion_tag("assistant/_chat.html", takes_context=True)
def assistant_chat(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if not settings.ASSISTANT_LLM_API_KEY or user is None or not is_admin(user):
        return {"offered": False}
    competition = context.get("competition")
    conversation = _conversation(request, competition)
    first = _("What would you like to change in this event?") if competition else _("What event would you like to add?")
    return {
        "offered": True,
        "history": [{"role": m.role, "text": m.text} for m in conversation.messages.all()] if conversation else [],
        "config": {
            "conversationId": conversation.pk if conversation else None,
            "competitionId": competition.pk if competition else None,
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
