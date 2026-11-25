import re
from http import HTTPStatus

from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.parser import Parser

# Text no column can store: the NUL character, and a lone surrogate -- half of a UTF-16 pair, which a JSON escape
# ("\ud83d") writes alone and UTF-8 cannot hold.
_UNSTORABLE = re.compile(r"[\x00\ud800-\udfff]")


def _carries_unstorable(value) -> bool:
    if isinstance(value, str):
        return _UNSTORABLE.search(value) is not None
    if isinstance(value, dict):
        return any(_carries_unstorable(key) or _carries_unstorable(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_carries_unstorable(item) for item in value)
    return False


UNSTORABLE_TEXT = "Text must not contain the NUL character or a lone surrogate (half of a UTF-16 pair)"


class _UnstorableTextError(ValueError):
    """The parser's refusal. Raised while ninja reads a body, it comes wrapped in ninja's 400 "Cannot
    parse request body"; `_http_error` answers it as the 422 it is."""


class _TextParser(Parser):
    """Ninja's parser, refusing the NUL character and the lone surrogate no text column can hold.

    Neither can be saved, so a title that carried one came back as a 500 instead of a 422; the site's
    own forms refuse NUL field by field (Django's ProhibitNullCharactersValidator).
    """

    def parse_body(self, request):
        data = super().parse_body(request)
        if _carries_unstorable(data):
            raise _UnstorableTextError(UNSTORABLE_TEXT)
        return data

    def parse_querydict(self, data, list_fields, request):
        result = super().parse_querydict(data, list_fields, request)
        if _carries_unstorable(result):
            raise _UnstorableTextError(UNSTORABLE_TEXT)
        return result


api = NinjaAPI(
    title="UniversalBikeTeam API",
    version="1.0.0",
    urls_namespace="api_v1",
    parser=_TextParser(),
    description=(
        "REST API for UniversalBikeTeam cycling portal. "
        "Authenticate via `Authorization: Bearer <your_api_token>` header. "
        "Obtain your token in your profile page."
    ),
)


def _register_routers() -> None:
    from api.endpoints.competitions import router as competitions_router
    from api.endpoints.content import knowledge_router, news_router
    from api.endpoints.disciplines import event_types_router
    from api.endpoints.disciplines import router as disciplines_router
    from api.endpoints.event_photos import router as event_photos_router
    from api.endpoints.gallery import router as gallery_router
    from api.endpoints.home import router as home_router
    from api.endpoints.live_stats import router as live_stats_router
    from api.endpoints.locations import router as locations_router
    from api.endpoints.managing import router as managing_router
    from api.endpoints.participants import router as participants_router
    from api.endpoints.protocols import router as protocols_router
    from api.endpoints.ratings import router as ratings_router
    from api.endpoints.registrations import router as registrations_router
    from api.endpoints.service_accounts import router as service_accounts_router
    from api.endpoints.start_list import router as start_list_router
    from api.endpoints.stats import router as stats_router
    from api.endpoints.timings import (
        finish_times_router,
        group_times_router,
        remote_points_router,
    )
    from api.endpoints.version import router as version_router
    from api.endpoints.virtual_members import router as virtual_members_router
    from api.endpoints.virtual_ride import router as virtual_ride_router
    from assistant.api import router as assistant_router

    api.add_router("/competitions/", competitions_router)
    api.add_router("/news/", news_router)
    api.add_router("/knowledge/", knowledge_router)
    api.add_router("/locations/", locations_router)
    api.add_router("/disciplines/", disciplines_router)
    api.add_router("/event-types/", event_types_router)
    api.add_router("/participants/", participants_router)
    api.add_router("/protocols/", protocols_router)
    api.add_router("/start-list/", start_list_router)
    api.add_router("/group-times/", group_times_router)
    api.add_router("/finish-times/", finish_times_router)
    api.add_router("/remote-points/", remote_points_router)
    api.add_router("/live-stats/", live_stats_router)
    api.add_router("/gallery/", gallery_router)
    api.add_router("/home/", home_router)
    api.add_router("/event-photos/", event_photos_router)
    api.add_router("/virtual-ride/", virtual_ride_router)
    api.add_router("/managing/", managing_router)
    api.add_router("/virtual-members/", virtual_members_router)
    api.add_router("/registrations/", registrations_router)
    api.add_router("/assistant/", assistant_router)
    api.add_router("/stats/", stats_router)
    api.add_router("/service-accounts/", service_accounts_router)
    api.add_router("/ratings/", ratings_router)
    api.add_router("/version/", version_router)


_register_routers()


@api.exception_handler(_UnstorableTextError)
def _unstorable_text(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=HTTPStatus.UNPROCESSABLE_ENTITY)


@api.exception_handler(HttpError)
def _http_error(request, exc):
    # Ninja's own answer for every other HttpError, word for word.
    if isinstance(exc.__cause__, _UnstorableTextError):
        return _unstorable_text(request, exc.__cause__)
    return api.create_response(request, {"detail": str(exc)}, status=exc.status_code)
