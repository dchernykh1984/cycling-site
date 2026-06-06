from typing import ClassVar

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError

from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    fieldsets = [*(BaseUserAdmin.fieldsets or []), ("Role", {"fields": ("role",)})]  # noqa: RUF012
    add_fieldsets = [*(BaseUserAdmin.add_fieldsets or []), ("Role", {"fields": ("role",)})]  # noqa: RUF012

    PRIVILEGE_FIELDS: ClassVar[tuple[str, ...]] = (
        "is_staff",
        "is_superuser",
        "groups",
        "user_permissions",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not (request.user.is_superuser or getattr(request.user, "role", "") == User.Role.OWNER):
            readonly.extend(f for f in self.PRIVILEGE_FIELDS if f not in readonly)
        return readonly

    def get_form(self, request, obj=None, **kwargs):
        """Restrict role changes to those the editing user is permitted to make."""
        base_form = super().get_form(request, obj, **kwargs)
        editor = request.user

        class RoleRestrictedForm(base_form):  # type: ignore[valid-type]
            def clean_role(self):
                role = self.cleaned_data.get("role")
                if role:
                    if obj is not None and not editor.can_manage_user(obj):
                        raise ValidationError("You don't have permission to edit this user's role.")
                    if not editor.can_assign_role(role):
                        raise ValidationError("You don't have permission to assign this role.")
                return role

        return RoleRestrictedForm
