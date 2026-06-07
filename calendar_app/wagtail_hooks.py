from typing import ClassVar

from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Competition, CyclingDiscipline, EventType


class EventTypeViewSet(SnippetViewSet):
    model = EventType
    icon = "tag"
    menu_label = "Event types"
    menu_order = 300
    list_display: ClassVar[list] = ["name"]
    panels: ClassVar[list] = [
        FieldPanel("name_ru"),
        FieldPanel("name_kk"),
        FieldPanel("name_en"),
    ]


class CyclingDisciplineViewSet(SnippetViewSet):
    model = CyclingDiscipline
    icon = "tag"
    menu_label = "Disciplines"
    menu_order = 310
    list_display: ClassVar[list] = ["name"]
    panels: ClassVar[list] = [
        FieldPanel("name_ru"),
        FieldPanel("name_kk"),
        FieldPanel("name_en"),
    ]


class CompetitionViewSet(SnippetViewSet):
    model = Competition
    icon = "calendar-alt"
    menu_label = "Competitions"
    menu_order = 320
    list_display: ClassVar[list] = ["title", "date_start", "event_type", "discipline", "status", "submitted_by"]
    list_filter: ClassVar[list] = ["status", "event_type", "discipline"]
    search_fields: ClassVar[list] = ["title_ru", "title_kk", "title_en"]
    panels: ClassVar[list] = [
        MultiFieldPanel(
            [FieldPanel("title_ru"), FieldPanel("title_kk"), FieldPanel("title_en")],
            heading="Title",
        ),
        MultiFieldPanel(
            [FieldPanel("description_ru"), FieldPanel("description_kk"), FieldPanel("description_en")],
            heading="Description",
        ),
        FieldPanel("event_type"),
        FieldPanel("discipline"),
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
register_snippet(CyclingDisciplineViewSet)
register_snippet(CompetitionViewSet)
