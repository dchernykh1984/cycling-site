from modeltranslation.translator import TranslationOptions, register

from .models import Competition, CyclingDiscipline, EventType


@register(EventType)
class EventTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(CyclingDiscipline)
class CyclingDisciplineTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Competition)
class CompetitionTranslationOptions(TranslationOptions):
    fields = ("title", "description")
