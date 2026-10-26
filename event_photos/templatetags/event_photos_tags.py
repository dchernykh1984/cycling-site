from django import template

from event_photos.models import ExternalAlbum
from event_photos.permissions import can_manage_albums
from event_photos.views import my_registrations, visible_albums

register = template.Library()


@register.simple_tag(takes_context=True)
def event_photo_section(context, competition):
    """What the event page offers about its external photo albums."""
    user = context["request"].user
    albums = visible_albums(user, competition)
    return {
        "has_albums": albums.exists(),
        "registrations": list(my_registrations(user, competition)) if albums.exists() else [],
        "can_manage": can_manage_albums(user, competition),
    }


@register.simple_tag(takes_context=True)
def my_race_photos(context):
    """The member's own registrations at events that have external albums, newest event first."""
    user = context["request"].user
    if not user.is_authenticated:
        return []
    events = ExternalAlbum.objects.filter(is_hidden=False).values("competition_id")
    return list(
        user.competition_registrations.filter(
            competition_id__in=events, competition__is_deleted=False, is_rejected=False
        )
        .select_related("competition")
        .order_by("-competition__date_start", "-pk")
    )
