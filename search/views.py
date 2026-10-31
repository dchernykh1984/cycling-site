from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.template.response import TemplateResponse
from django.utils.translation import get_language
from wagtail.models import Locale, Page
from wagtail.search.backends import get_search_backend

from calendar_app.models import Competition
from calendar_app.visibility import can_see
from knowledge.models import KnowledgeArticle
from locations.models import Location, location_visible_to
from news.models import NewsArticle


def search(request):
    search_query = request.GET.get("query", None)
    page = request.GET.get("page", 1)

    if search_query:
        search_results = Page.objects.live().filter(locale=Locale.get_active()).search(search_query)
        backend = get_search_backend()
        competition_results = [
            comp
            for comp in backend.search(
                search_query,
                Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False),
            )
            # Filtered after the search rather than in it: the search backend accepts only plain
            # field filters, and the invite check is a join. There are few such events to drop.
            if not comp.invite_only or can_see(request.user, comp)
        ]
        knowledge_results = list(
            backend.search(
                search_query,
                KnowledgeArticle.objects.filter(locale=get_language() or "ru", is_deleted=False, is_hidden=False),
            )
        )
        news_results = list(backend.search(search_query, NewsArticle.objects.filter(is_deleted=False, is_hidden=False)))
        location_results = [
            place
            for place in backend.search(
                search_query, Location.objects.filter(is_deleted=False, is_hidden=False).select_related("proposal")
            )
            # A place awaiting review is its proposer's and its moderators' (FR-LOC-003): dropped after
            # the search, like an invite-only event above, since a proposal is a join too.
            if location_visible_to(place, request.user)
        ]
    else:
        search_results = Page.objects.none()
        competition_results = []
        knowledge_results = []
        news_results = []
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
            "knowledge_results": knowledge_results,
            "news_results": news_results,
            "location_results": location_results,
        },
    )
