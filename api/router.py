from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.parser import Parser


def _carries_nul(value) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_carries_nul(key) or _carries_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_carries_nul(item) for item in value)
    return False


NUL_IN_TEXT = "Text must not contain the NUL character"


class _NulInTextError(ValueError):
    """The parser's refusal. Raised while ninja reads a body, it comes wrapped in ninja's 400 "Cannot
    parse request body"; `_http_error` answers it as the 422 it is."""


class _TextParser(Parser):
    """Ninja's parser, refusing the NUL character no text column can hold.

    PostgreSQL rejects it on save, so a title that carried one came back as a 500 instead of a 422;
    the site's own forms refuse it field by field (Django's ProhibitNullCharactersValidator).
    """

    def parse_body(self, request):
        data = super().parse_body(request)
        if _carries_nul(data):
            raise _NulInTextError(NUL_IN_TEXT)
        return data

    def parse_querydict(self, data, list_fields, request):
        result = super().parse_querydict(data, list_fields, request)
        if _carries_nul(result):
            raise _NulInTextError(NUL_IN_TEXT)
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
    from api.endpoints.start_list import router as start_list_router
    from api.endpoints.timings import (
        finish_times_router,
        group_times_router,
        remote_points_router,
    )
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
    api.add_router("/assistant/", assistant_router)


_register_routers()


@api.exception_handler(_NulInTextError)
def _nul_in_text(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=422)


@api.exception_handler(HttpError)
def _http_error(request, exc):
    # Ninja's own answer for every other HttpError, word for word.
    if isinstance(exc.__cause__, _NulInTextError):
        return _nul_in_text(request, exc.__cause__)
    return api.create_response(request, {"detail": str(exc)}, status=exc.status_code)
