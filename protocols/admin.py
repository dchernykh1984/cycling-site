from django.contrib import admin

from .models import Protocol, ProtocolVersion, StartListUpload


@admin.register(Protocol)
class ProtocolAdmin(admin.ModelAdmin):
    list_display = ("competition", "protocol_type", "is_live", "last_updated", "stage_label")
    list_filter = ("protocol_type", "is_live")
    raw_id_fields = ("competition",)


@admin.register(ProtocolVersion)
class ProtocolVersionAdmin(admin.ModelAdmin):
    list_display = ("protocol", "saved_at", "file_hash")
    raw_id_fields = ("protocol",)


@admin.register(StartListUpload)
class StartListUploadAdmin(admin.ModelAdmin):
    list_display = ("competition", "device_id", "updated_at")
    search_fields = ("device_id",)
    raw_id_fields = ("competition",)
