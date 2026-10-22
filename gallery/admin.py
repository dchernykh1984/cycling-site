from django.contrib import admin

from gallery.models import Album, Photo


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    fields = ("image", "caption", "sort_order")
    readonly_fields = ("image",)


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "competition", "is_hidden", "created_by")
    list_filter = ("is_hidden",)
    search_fields = ("title",)
    raw_id_fields = ("competition", "cover", "created_by")
    inlines = (PhotoInline,)
