from modeltranslation.translator import TranslationOptions, register

from .models import NewsArticle


@register(NewsArticle)
class NewsArticleTranslationOptions(TranslationOptions):
    fields = ("title", "intro", "body")
