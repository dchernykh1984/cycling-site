from typing import ClassVar

from django.contrib import admin

from .models import CompetitionRegistration, RegistrationCategory, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "is_deleted", "created_at")
    list_filter = ("is_deleted",)
    search_fields = ("name",)
    actions: ClassVar[list[str]] = ["mark_deleted"]  # type: ignore[misc]

    @admin.action(description="Mark selected teams as deleted")
    def mark_deleted(self, request, queryset):
        queryset.update(is_deleted=True)


@admin.register(RegistrationCategory)
class RegistrationCategoryAdmin(admin.ModelAdmin):
    list_display = ("competition", "name", "male", "female", "is_deleted")
    list_filter = ("is_deleted",)
    raw_id_fields = ("competition",)


@admin.register(CompetitionRegistration)
class CompetitionRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "competition",
        "last_name",
        "first_name",
        "gender",
        "category",
        "is_approved",
        "is_paid",
        "is_rejected",
    )
    list_filter = ("is_approved", "is_paid", "is_rejected")
    raw_id_fields = ("competition", "user", "registered_by", "category", "team")
