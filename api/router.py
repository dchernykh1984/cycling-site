from ninja import NinjaAPI

api = NinjaAPI(
    title="UniversalBikeTeam API",
    version="1.0.0",
    urls_namespace="api_v1",
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
    from api.endpoints.locations import router as locations_router
    from api.endpoints.participants import router as participants_router
    from api.endpoints.protocols import router as protocols_router

    api.add_router("/competitions/", competitions_router)
    api.add_router("/news/", news_router)
    api.add_router("/knowledge/", knowledge_router)
    api.add_router("/locations/", locations_router)
    api.add_router("/disciplines/", disciplines_router)
    api.add_router("/event-types/", event_types_router)
    api.add_router("/participants/", participants_router)
    api.add_router("/protocols/", protocols_router)


_register_routers()
