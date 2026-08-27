"""Helpers the pager needs and Django templates cannot express.

``Paginator.get_elided_page_range`` takes the current page as an argument, which template syntax
cannot pass, so it is wrapped as a filter here.
"""

from django import template

register = template.Library()


@register.filter
def elided_page_range(page_obj):
    """Page numbers around the current one, with Django's ellipsis marker where numbers are skipped.

    A crawler can only follow links it can see. With prev/next alone it has to walk 26 pages of
    competitions in a chain, one request at a time; with a window plus the first and last page it
    reaches any page in a couple of hops.
    """
    try:
        return page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)
    except (AttributeError, TypeError):  # pragma: no cover - defensive: not a real Page
        return []


@register.simple_tag(takes_context=True)
def page_query(context, page_number):
    """The current query string with ``page`` replaced, so filters survive a page change."""
    request = context.get("request")
    if request is None:  # pragma: no cover - defensive
        return f"?page={page_number}"
    params = request.GET.copy()
    params["page"] = page_number
    return f"?{params.urlencode()}"
