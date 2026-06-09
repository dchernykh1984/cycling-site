from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.template.response import TemplateResponse
from wagtail.models import Locale, Page
from wagtail.search.backends import get_search_backend

from calendar_app.models import Competition
from locations.models import Location


def search(request):
    search_query = request.GET.get("query", None)
    page = request.GET.get("page", 1)

    if search_query:
        search_results = Page.objects.live().filter(locale=Locale.get_active()).search(search_query)
        backend = get_search_backend()
        competition_results = list(
            backend.search(
                search_query,
                Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False),
            )
        )
        location_results = list(
            backend.search(search_query, Location.objects.filter(is_deleted=False, is_hidden=False))
        )
    else:
        search_results = Page.objects.none()
        competition_results = []
        location_results = []

    paginator = Paginator(search_results, 10)
    try:
        search_results = paginator.page(page)
    except PageNotAnInteger:
        search_results = paginator.page(1)
    except EmptyPage:
        search_results = paginator.page(paginator.num_pages)

    return TemplateResponse(
        request,
        "search/search.html",
        {
            "search_query": search_query,
            "search_results": search_results,
            "competition_results": competition_results,
            "location_results": location_results,
        },
    )
