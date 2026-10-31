from modeltranslation.translator import TranslationOptions, register

from .models import HomeCard, SiteContent


@register(SiteContent)
class SiteContentTranslationOptions(TranslationOptions):
    fields = ("navbar_title", "page_title")


@register(HomeCard)
class HomeCardTranslationOptions(TranslationOptions):
    fields = ("title", "body")
