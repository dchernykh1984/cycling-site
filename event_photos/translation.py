from modeltranslation.translator import TranslationOptions, register

from event_photos.models import ExternalAlbum


@register(ExternalAlbum)
class ExternalAlbumTranslationOptions(TranslationOptions):
    fields = ("title", "credit")
