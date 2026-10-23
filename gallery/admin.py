from django.contrib import admin
from modeltranslation.admin import TranslationAdmin, TranslationTabularInline

from gallery.models import Album, Photo


class PhotoInline(TranslationTabularInline):
    model = Photo
    extra = 0
    fields = ("image", "caption", "sort_order")
    readonly_fields = ("image",)


@admin.register(Album)
class AlbumAdmin(TranslationAdmin):
    list_display = ("title", "date", "competition", "is_hidden", "created_by")
    list_filter = ("is_hidden",)
    search_fields = ("title_ru", "title_kk", "title_en")
    raw_id_fields = ("competition", "cover", "created_by")
    inlines = (PhotoInline,)
