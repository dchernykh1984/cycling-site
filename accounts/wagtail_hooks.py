from typing import ClassVar

from django.templatetags.static import static
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.admin.userbar import AccessibilityItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import CreateView, EditView, SnippetViewSet

from accounts.models import User


@hooks.register("insert_global_admin_css")
def admin_dark_mode_css():
    return format_html('<link rel="stylesheet" href="{}">', static("css/admin_dark.css"))


@hooks.register("construct_wagtail_userbar")
def disable_button_name_axe_rule(_request, items):
    for item in items:
        if isinstance(item, AccessibilityItem):
            item.axe_run_only = [r for r in item.axe_run_only if r != "button-name"]


class _RoleEnforcedMixin:
    """Reject role changes the current editor is not permitted to make."""

    def form_valid(self, form):
        editor = self.request.user
        new_role = form.cleaned_data.get("role")
        if new_role:
            target = getattr(self, "object", None)
            if target is not None and not editor.can_manage_user(target):
                form.add_error("role", "You don't have permission to edit this user's role.")
                return self.form_invalid(form)
            if not editor.can_assign_role(new_role):
                form.add_error("role", "You don't have permission to assign this role.")
                return self.form_invalid(form)
        return super().form_valid(form)


class UserCreateView(_RoleEnforcedMixin, CreateView):
    pass


class UserEditView(_RoleEnforcedMixin, EditView):
    pass


class UserViewSet(SnippetViewSet):
    model = User
    menu_label = "Users"
    icon = "user"
    menu_order = 300
    copy_view_enabled = False
    add_view_class = UserCreateView
    edit_view_class = UserEditView
    list_display: ClassVar[list[str]] = ["username", "email", "role", "is_active", "date_joined"]
    list_filter: ClassVar[list[str]] = ["role", "is_active"]
    search_fields: ClassVar[list[str]] = ["username", "email"]
    panels: ClassVar[list] = [
        MultiFieldPanel(
            [
                FieldPanel("username"),
                FieldPanel("email"),
                FieldPanel("first_name"),
                FieldPanel("last_name"),
            ],
            heading="Personal info",
        ),
        MultiFieldPanel(
            [
                FieldPanel("role"),
                FieldPanel("is_active"),
            ],
            heading="Role & status",
        ),
    ]


register_snippet(UserViewSet)
