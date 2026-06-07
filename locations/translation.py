from modeltranslation.translator import TranslationOptions, register

from .models import Location


@register(Location)
class LocationTranslationOptions(TranslationOptions):
    fields = ("name",)
