from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "object_type", "object_id", "object_repr")
    list_filter = ("action", "object_type")
    search_fields = ("object_repr", "object_id", "user__username", "user__email")
    readonly_fields = ("timestamp", "user", "action", "object_type", "object_id", "object_repr", "changes")
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
