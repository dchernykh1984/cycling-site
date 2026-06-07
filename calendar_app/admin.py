from __future__ import annotations

from django.contrib import admin

from .models import Competition


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("title", "date_start", "status", "submitted_by")
    list_filter = ("status",)
    readonly_fields = ("upload_token",)
    search_fields = ("title_ru", "title_kk", "title_en")
