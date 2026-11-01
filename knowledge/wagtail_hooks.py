from typing import ClassVar

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.widgets.button import ListingButton
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from accounts import roles
from knowledge.models import DraftSubmission


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
        if not roles.at_least(request.user, roles.MANAGE_KNOWLEDGE):
            raise PermissionDenied
        sub = get_object_or_404(DraftSubmission, pk=pk)
        if sub.status != DraftSubmission.Status.PENDING:
            messages.error(request, f"Cannot approve: submission is already '{sub.get_status_display()}'.")
            return redirect(reverse(self.get_url_name("list")))
        if request.method == "POST":
            try:
                sub.approve(reviewer=request.user)
                messages.success(request, f"Submission '{sub.title}' approved and published.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(reverse(self.get_url_name("list")))
        return render(
            request,
            "knowledge/admin/approve_confirm.html",
            {"submission": sub, "cancel_url": reverse(self.get_url_name("list"))},
        )

    def reject_view(self, request, pk):
        if not roles.at_least(request.user, roles.MANAGE_KNOWLEDGE):
            raise PermissionDenied
        sub = get_object_or_404(DraftSubmission, pk=pk)
        if sub.status != DraftSubmission.Status.PENDING:
            messages.error(request, f"Cannot reject: submission is already '{sub.get_status_display()}'.")
            return redirect(reverse(self.get_url_name("list")))
        if request.method == "POST":
            note = request.POST.get("reviewer_note", "")
            try:
                sub.reject(reviewer=request.user, note=note)
                messages.success(request, f"Submission '{sub.title}' rejected.")
            except ValueError as exc:  # reviewed by someone else since the page was opened
                messages.error(request, str(exc))
            return redirect(reverse(self.get_url_name("list")))
        return render(
            request,
            "knowledge/admin/reject_form.html",
            {"submission": sub, "cancel_url": reverse(self.get_url_name("list"))},
        )


register_snippet(DraftSubmissionViewSet)


@hooks.register("register_snippet_listing_buttons")
def draft_submission_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, DraftSubmission):
        return
    if snippet.status != DraftSubmission.Status.PENDING:
        return
    viewset = snippet.snippet_viewset
    approve_url = reverse(viewset.get_url_name("approve"), args=[snippet.pk])
    reject_url = reverse(viewset.get_url_name("reject"), args=[snippet.pk])
    yield ListingButton("Approve", approve_url, priority=10)
    yield ListingButton("Reject", reject_url, priority=20)
