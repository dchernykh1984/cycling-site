from ninja import Router, Schema
from ninja.errors import HttpError

from api.auth import ApiTokenAuth
from api.schemas import LocalizedStr, localize_field
from calendar_app.models import Discipline, DisciplineCategory, EventType

auth = ApiTokenAuth()
router = Router(tags=["disciplines"])
event_types_router = Router(tags=["event-types"])


# -- Schemas -------------------------------------------------------------------


class DisciplineOut(Schema):
    id: int
    name: LocalizedStr

    @staticmethod
    def resolve_name(obj: Discipline) -> LocalizedStr:
        return localize_field(obj, "name")


class DisciplineCategoryOut(Schema):
    id: int
    name: LocalizedStr
    disciplines: list[DisciplineOut]

    @staticmethod
    def resolve_name(obj: DisciplineCategory) -> LocalizedStr:
        return localize_field(obj, "name")

    @staticmethod
    def resolve_disciplines(obj: DisciplineCategory) -> list[Discipline]:
        return list(obj.disciplines.all())


class EventTypeOut(Schema):
    id: int
    name: LocalizedStr

    @staticmethod
    def resolve_name(obj: EventType) -> LocalizedStr:
        return localize_field(obj, "name")


# -- Endpoints -----------------------------------------------------------------


@router.get("/", response=list[DisciplineCategoryOut], auth=auth, summary="List discipline categories with disciplines")
def list_disciplines(request):
    categories = DisciplineCategory.objects.prefetch_related("disciplines").order_by("order")
    return list(categories)


@router.get("/{category_id}", response=DisciplineCategoryOut, auth=auth, summary="Get discipline category")
def get_discipline_category(request, category_id: int):
    try:
        return DisciplineCategory.objects.prefetch_related("disciplines").get(pk=category_id)
    except DisciplineCategory.DoesNotExist:
        raise HttpError(404, "Discipline category not found") from None


@event_types_router.get("/", response=list[EventTypeOut], auth=auth, summary="List event types")
def list_event_types(request):
    return list(EventType.objects.order_by("order"))
