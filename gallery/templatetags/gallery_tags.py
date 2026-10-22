from django import template

from gallery.models import Album

register = template.Library()


@register.simple_tag(takes_context=True)
def competition_albums(context, competition):
    """The albums of an event the reader may see, for the event page."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None:
        return Album.objects.none()
    return Album.objects.visible_to(user).filter(competition=competition)
