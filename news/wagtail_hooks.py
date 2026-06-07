from typing import ClassVar

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from news.models import Comment


class CommentViewSet(SnippetViewSet):
    model = Comment
    list_display: ClassVar[list] = ["__str__", "page", "author", "is_approved", "created_at"]
    list_filter: ClassVar[list] = ["is_approved"]
    search_fields: ClassVar[list] = ["body", "author__email"]


register_snippet(CommentViewSet)
