"""Counting the pages robots and the team are sent (issue #184).

People count themselves: their browser runs the page's script, which tells the site it opened the
page (api.endpoints.stats). A robot can call itself a browser, but it seldom runs scripts. Robots are
counted here, by what their User-Agent says they are, and so are the owners' and admins' own pages.
"""

import logging
from http import HTTPStatus

from django.db import DatabaseError

from cycling_site.middleware import SiteLocaleMiddleware
from stats import counting
from stats.models import Tally
from stats.robots import robot

logger = logging.getLogger(__name__)


def _a_page(request, response) -> bool:
    """A page somebody opened: an HTML answer to GET, outside the API, the admin and the files."""
    return (
        request.method == "GET"
        and response.status_code == HTTPStatus.OK
        and not response.streaming
        and response.get("Content-Type", "").startswith("text/html")
        and not request.path_info.startswith(SiteLocaleMiddleware.LANGUAGE_FREE_PREFIXES)
    )


def count_page(request) -> None:
    user_agent = request.headers.get("User-Agent", "")
    # A request that names nothing is nobody we can say anything about.
    if not user_agent.strip():
        return
    if counting.is_team(request.user):
        counting.add((Tally.Dimension.VIEWS, Tally.Audience.TEAM), (Tally.Dimension.TEAM, str(request.user.pk)))
        return
    found = robot(user_agent)
    if found:
        counting.add((Tally.Dimension.VIEWS, Tally.Audience.BOTS), (Tally.Dimension.BOT, ":".join(found)))


class CountingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if _a_page(request, response):
            try:
                count_page(request)
            except DatabaseError:  # statistics never cost anybody the page
                logger.exception("a page view could not be counted")
        return response
