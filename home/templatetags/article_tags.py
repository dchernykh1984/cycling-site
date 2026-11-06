"""Template helpers for the text of an article or a news item as its readers get it."""

from django.template import Library

from cycling_site.contents import with_contents

register = Library()

# Anchors on the headings, and the contents list where the text asks for one (cycling_site.contents)
register.filter("with_contents", with_contents)
