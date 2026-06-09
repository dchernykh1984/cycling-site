from urllib.parse import urlparse

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import View

from accounts.models import User

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def _can_manage_locations(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


class LocationDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        location.is_deleted = True
        location.save(update_fields=["is_deleted"])
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)


class LocationHideView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        location.is_hidden = not location.is_hidden
        location.save(update_fields=["is_hidden"])
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)
