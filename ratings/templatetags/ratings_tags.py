"""The organizer's rating beside an event (issue #436)."""

from django.template import Library

from ratings import scores

register = Library()


@register.simple_tag
def organizer_rating(competition):
    """The rating of the member who posted ``competition``, or None while there is none to show."""
    return scores.of_organizer(competition.submitted_by)
