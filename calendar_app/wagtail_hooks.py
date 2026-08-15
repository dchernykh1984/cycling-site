from typing import ClassVar

from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Competition, Discipline, DisciplineCategory, EventType


class CompetitionFilterSet(WagtailFilterSet):
    class Meta:
        model = Competition
        fields: ClassVar[list] = ["status", "event_types", "disciplines__category", "disciplines"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The auto-generated category filter spans the disciplines M2M with a plain
        # ModelChoiceFilter (distinct=False), so a competition with several disciplines of one
        # category shows up multiple times. Force distinct() to collapse the duplicate rows.
        self.filters["disciplines__category"].distinct = True


class EventTypeViewSet(SnippetViewSet):
    model = EventType
    icon = "tag"
    menu_label = "Event types"
    menu_order = 300
    list_display: ClassVar[list] = ["name", "order"]
    panels: ClassVar[list] = [
        FieldPanel("name_ru"),
        FieldPanel("name_kk"),
        FieldPanel("name_en"),
        FieldPanel("order"),
    ]


class DisciplineCategoryViewSet(SnippetViewSet):
    model = DisciplineCategory
    icon = "list-ul"
    menu_label = "Directions"
    menu_order = 305
    list_display: ClassVar[list] = ["name", "order"]
    panels: ClassVar[list] = [
        FieldPanel("name_ru"),
        FieldPanel("name_kk"),
        FieldPanel("name_en"),
        FieldPanel("order"),
    ]


class DisciplineViewSet(SnippetViewSet):
    model = Discipline
    icon = "tag"
    menu_label = "Disciplines"
    menu_order = 310
    list_display: ClassVar[list] = ["name", "category", "order"]
    list_filter: ClassVar[list] = ["category"]
    panels: ClassVar[list] = [
        FieldPanel("category"),
        FieldPanel("name_ru"),
        FieldPanel("name_kk"),
        FieldPanel("name_en"),
        FieldPanel("order"),
    ]


class CompetitionViewSet(SnippetViewSet):
    model = Competition
    icon = "calendar-alt"
    menu_label = "Competitions"
    menu_order = 320
    list_display: ClassVar[list] = [
        "title",
        "date_start",
        "event_type_label",
        "disciplines_label",
        "status",
        "submitted_by",
    ]
    filterset_class = CompetitionFilterSet
    search_fields: ClassVar[list] = ["title_ru", "title_kk", "title_en"]

    def get_queryset(self, request):
        # The two labels in list_display walk a many-to-many per row; prefetch to avoid N+1.
        return Competition.objects.prefetch_related("disciplines", "event_types")

    panels: ClassVar[list] = [
        MultiFieldPanel(
            [FieldPanel("title_ru"), FieldPanel("title_kk"), FieldPanel("title_en")],
            heading="Title",
        ),
        MultiFieldPanel(
            [FieldPanel("description_ru"), FieldPanel("description_kk"), FieldPanel("description_en")],
            heading="Description",
        ),
        FieldPanel("event_types"),
        FieldPanel("disciplines"),
        FieldPanel("location"),
        FieldPanel("date_start"),
        FieldPanel("date_end"),
        FieldPanel("status"),
        FieldPanel("submitted_by"),
        FieldPanel("approved_by"),
        FieldPanel("approved_at"),
        FieldPanel("rejection_reason"),
        FieldPanel("url_announcement"),
        FieldPanel("url_registration"),
        FieldPanel("url_route"),
        FieldPanel("url_regulations"),
        FieldPanel("url_results"),
        MultiFieldPanel(
            [FieldPanel("upload_token", read_only=True)],
            heading="Protocol upload",
        ),
    ]


register_snippet(EventTypeViewSet)
register_snippet(DisciplineCategoryViewSet)
register_snippet(DisciplineViewSet)
register_snippet(CompetitionViewSet)
