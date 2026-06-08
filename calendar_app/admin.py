from __future__ import annotations

from typing import ClassVar

from django.contrib import admin
from django.db import models
from django.forms import Textarea

from .models import Competition, CompetitionComment


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("title", "date_start", "status", "submitted_by")
    list_filter = ("status",)
    readonly_fields = ("upload_token",)
    search_fields = ("title_ru", "title_kk", "title_en")


@admin.register(CompetitionComment)
class CompetitionCommentAdmin(admin.ModelAdmin):
    list_display = ("competition", "author", "created_at")
    list_filter = ("competition",)
    readonly_fields = ("created_at",)
    search_fields = ("body", "author__email")
    formfield_overrides: ClassVar[dict] = {
        models.CharField: {"widget": Textarea(attrs={"rows": 4, "cols": 80})},
    }
