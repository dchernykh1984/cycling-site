from modeltranslation.translator import TranslationOptions, register

from protocols.models import ProtocolSection


@register(ProtocolSection)
class ProtocolSectionTranslationOptions(TranslationOptions):
    fields = ("name",)
