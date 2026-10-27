from django.contrib import admin

from .models import GroupRide, GroupRideMember, VirtualRide


@admin.register(VirtualRide)
class VirtualRideAdmin(admin.ModelAdmin):
    list_display = ("user", "route", "kind", "duration_s", "distance_m", "power_source", "finished_at")
    list_filter = ("kind", "power_source", "route")
    search_fields = ("user__email", "user__first_name", "user__last_name", "route")
    raw_id_fields = ("user", "group")


class GroupRideMemberInline(admin.TabularInline):
    model = GroupRideMember
    raw_id_fields = ("user",)
    extra = 0


@admin.register(GroupRide)
class GroupRideAdmin(admin.ModelAdmin):
    list_display = ("route", "host", "start_at", "cancelled")
    list_filter = ("cancelled", "route")
    raw_id_fields = ("host",)
    inlines = (GroupRideMemberInline,)
