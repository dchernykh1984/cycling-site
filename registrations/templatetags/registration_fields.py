"""The registration page's own fields (registrations/_person_fields.html), laid out by the page itself."""

from django import template

from cycling_site.typed_date import TypedDateInput

register = template.Library()


@register.simple_tag
def typed_date(bound, field_id, css="", required=False):
    """A date typed as DD.MM.YYYY with its calendar button (cycling_site/typed_date.py) for a field the page lays out
    itself: its id and classes as the page names them -- a person's set of fields on the page for several has ids of
    its own -- required only where the page asks for it, and read-only, without its calendar, where the form says."""
    widget = bound.field.widget if isinstance(bound.field.widget, TypedDateInput) else TypedDateInput()
    base = "form-control-plaintext" if widget.attrs.get("readonly") else "form-control"
    attrs = {"id": field_id, "class": " ".join(filter(None, [base, css]))}
    if required:
        attrs["required"] = True
    if bound.errors:
        attrs["aria-invalid"] = "true"
    return widget.render(bound.html_name, bound.value(), attrs)
