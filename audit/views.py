from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import ListView

from .models import AuditLog


class AuditLogListView(UserPassesTestMixin, ListView):
    model = AuditLog
    template_name = "audit/auditlog_list.html"
    context_object_name = "entries"
    paginate_by = 50
    ordering = "-timestamp"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser
