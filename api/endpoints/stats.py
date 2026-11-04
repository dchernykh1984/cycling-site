"""The site's own statistics over the API (issue #184): a person's browser saying it opened a page."""

from http import HTTPStatus
from urllib.parse import urlsplit

from ninja import Field, Router, Schema, Status

from stats import counting
from stats.robots import robot

router = Router(tags=["stats"])


class HitIn(Schema):
    # A tally keeps a key's first characters (stats.counting.add): a long address is cut, not refused.
    path: str = Field(max_length=2000)
    referrer: str = Field("", max_length=2000)


def _from_our_page(request) -> bool:
    """Sent by a page of this site, as browsers mark it: never by another site's page."""
    if request.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
        return False
    origin = request.headers.get("Origin")
    return origin is None or urlsplit(origin).netloc == request.get_host()


@router.post("/hit", auth=None, response={HTTPStatus.NO_CONTENT: None}, summary="A browser opened a page")
def hit(request, payload: HitIn):
    """How people are counted: the page's own script (static/js/cycling_site.js) says it was opened. A
    robot can call itself a browser, but seldom runs scripts. Whatever does not look like a person on one
    of our pages is dropped without a word -- the browser does not wait for the answer."""
    user_agent = request.headers.get("User-Agent", "")
    if (
        _from_our_page(request)
        and user_agent.strip()
        and robot(user_agent) is None
        and not counting.is_team(request.user)
    ):
        counting.count_person(payload.path, payload.referrer, user_agent, request.get_host())
    return Status(HTTPStatus.NO_CONTENT, None)
