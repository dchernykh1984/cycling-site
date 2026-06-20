from typing import ClassVar

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.widgets.button import ListingButton
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from accounts.models import User
from knowledge.models import DraftSubmission

_LIST_URL_NAME = "wagtailsnippets_knowledge_draftsubmission:list"
_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def _can_manage_knowledge(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


class DraftSubmissionViewSet(SnippetViewSet):
    model = DraftSubmission
    menu_label = "Submissions"
    icon = "edit"
    menu_order = 200
    list_display: ClassVar[list] = [
        "title",
        "submission_type",
        "locale",
        "author",
        "status",
        "submitted_at",
    ]
    list_filter: ClassVar[list] = ["status", "submission_type", "locale"]
    search_fields: ClassVar[list] = ["title", "author__email"]

    def get_urlpatterns(self):
        conv = self.pk_path_converter
        return [
            *super().get_urlpatterns(),
            path(f"approve/<{conv}:pk>/", self.approve_view, name="approve"),
            path(f"reject/<{conv}:pk>/", self.reject_view, name="reject"),
        ]

    def approve_view(self, request, pk):
        if not _can_manage_knowledge(request.user):
            raise PermissionDenied
        sub = get_object_or_404(DraftSubmission, pk=pk)
        if sub.status != DraftSubmission.Status.PENDING:
            messages.error(request, f"Cannot approve: submission is already '{sub.get_status_display()}'.")
            return redirect(reverse(_LIST_URL_NAME))
        if request.method == "POST":
            try:
                sub.approve(reviewer=request.user)
                messages.success(request, f"Submission '{sub.title}' approved and published.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(reverse(_LIST_URL_NAME))
        return render(
            request,
            "knowledge/admin/approve_confirm.html",
            {"submission": sub, "cancel_url": reverse(_LIST_URL_NAME)},
        )

    def reject_view(self, request, pk):
        if not _can_manage_knowledge(request.user):
            raise PermissionDenied
        sub = get_object_or_404(DraftSubmission, pk=pk)
        if sub.status != DraftSubmission.Status.PENDING:
            messages.error(request, f"Cannot reject: submission is already '{sub.get_status_display()}'.")
            return redirect(reverse(_LIST_URL_NAME))
        if request.method == "POST":
            note = request.POST.get("reviewer_note", "")
            sub.reject(reviewer=request.user, note=note)
            messages.success(request, f"Submission '{sub.title}' rejected.")
            return redirect(reverse(_LIST_URL_NAME))
        return render(
            request,
            "knowledge/admin/reject_form.html",
            {"submission": sub, "cancel_url": reverse(_LIST_URL_NAME)},
        )


register_snippet(DraftSubmissionViewSet)


@hooks.register("register_snippet_listing_buttons")
def draft_submission_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, DraftSubmission):
        return
    if snippet.status != DraftSubmission.Status.PENDING:
        return
    approve_url = reverse("wagtailsnippets_knowledge_draftsubmission:approve", args=[snippet.pk])
    reject_url = reverse("wagtailsnippets_knowledge_draftsubmission:reject", args=[snippet.pk])
    yield ListingButton("Approve", approve_url, priority=10)
    yield ListingButton("Reject", reject_url, priority=20)
