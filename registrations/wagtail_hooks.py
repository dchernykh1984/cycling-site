from typing import ClassVar

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import DeleteView as SnippetDeleteView
from wagtail.snippets.views.snippets import SnippetViewSet

from accounts.models import User

from .models import Team


class TeamSoftDeleteView(SnippetDeleteView):
    def delete_action(self) -> None:
        self.object.is_deleted = True
        self.object.save(update_fields=["is_deleted"])


class TeamViewSet(SnippetViewSet):
    model = Team
    menu_label = "Teams"
    icon = "group"
    menu_order = 400
    delete_view_class = TeamSoftDeleteView
    list_display: ClassVar[list[str]] = ["name", "is_deleted", "created_at"]
    list_filter: ClassVar[list[str]] = ["is_deleted"]
    search_fields: ClassVar[list[str]] = ["name"]

    def user_has_any_permission(self, user, actions):
        if user.is_superuser:
            return True
        try:
            return user.get_role_rank() >= User.ROLE_HIERARCHY.index(User.Role.ADMIN)
        except (AttributeError, ValueError):
            return False

    def user_has_permission(self, user, action):
        return self.user_has_any_permission(user, [action])


register_snippet(TeamViewSet)
