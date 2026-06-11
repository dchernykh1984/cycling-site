from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from .views import AuditLogListView


@hooks.register("register_admin_urls")
def register_audit_urls():
    return [
        path("audit-log/", AuditLogListView.as_view(), name="audit_log_list"),
    ]


@hooks.register("register_admin_menu_item")
def register_audit_menu_item():
    return _AuditLogMenuItem(
        label="Audit Log",
        url=reverse("audit_log_list"),
        icon_name="list-ul",
        order=9000,
    )


class _AuditLogMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_superuser
