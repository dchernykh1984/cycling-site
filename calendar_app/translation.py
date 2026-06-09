from modeltranslation.translator import TranslationOptions, register

from .models import Competition, Discipline, DisciplineCategory, EventType


@register(EventType)
class EventTypeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(DisciplineCategory)
class DisciplineCategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Discipline)
class DisciplineTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Competition)
class CompetitionTranslationOptions(TranslationOptions):
    fields = ("title", "description")
