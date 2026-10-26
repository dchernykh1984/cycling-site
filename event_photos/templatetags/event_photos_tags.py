from django import template
from django.urls import reverse

from event_photos.actions import registration_summary
from event_photos.models import ExternalAlbum
from event_photos.permissions import can_manage_albums, can_see_event
from event_photos.views import my_registrations, visible_albums

register = template.Library()


@register.simple_tag(takes_context=True)
def event_photo_section(context, competition):
    """What the event page offers about its external photo albums."""
    user = context["request"].user
    albums = visible_albums(user, competition)
    return {
        "has_albums": albums.exists(),
        "registrations": [registration_summary(r) for r in my_registrations(user, competition)]
        if albums.exists()
        else [],
        "can_manage": can_manage_albums(user, competition),
    }


@register.simple_tag(takes_context=True)
def my_race_photos(context):
    """Cards of the member's own registrations at events with albums they may see, newest first."""
    user = context["request"].user
    if not user.is_authenticated:
        return []
    events = ExternalAlbum.objects.filter(is_hidden=False).values("competition_id")
    registrations = (
        user.competition_registrations.filter(competition_id__in=events, is_rejected=False)
        .select_related("competition", "category")
        .order_by("-competition__date_start", "-pk")
    )
    return [registration_summary(r) for r in registrations if can_see_event(user, r.competition)]


@register.simple_tag
def photo_thumb_url(photo):
    return reverse("event_photos:thumb", args=[photo.album.competition_id, photo.pk, photo.source_sha256[:16]])
