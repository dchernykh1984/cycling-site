from modeltranslation.translator import TranslationOptions, register

from .models import SiteContent


@register(SiteContent)
class SiteContentTranslationOptions(TranslationOptions):
    fields = ("navbar_title", "page_title", "body")
