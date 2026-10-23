from modeltranslation.translator import TranslationOptions, register

from gallery.models import Album, Photo


@register(Album)
class AlbumTranslationOptions(TranslationOptions):
    fields = ("title",)


@register(Photo)
class PhotoTranslationOptions(TranslationOptions):
    fields = ("caption",)
