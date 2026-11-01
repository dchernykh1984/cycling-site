from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.generic import CreateView, View
from wagtail.models import Locale

from accounts import roles
from accounts.access import ParticipantRequiredMixin
from cycling_site.forms import save_comment
from cycling_site.page_mixins import live_page_in
from knowledge.forms import AddKnowledgeArticleCommentForm, DraftSubmissionForm, KnowledgeArticleForm
from knowledge.models import DraftSubmission, KnowledgeArticle, KnowledgeArticleComment, KnowledgeIndexPage


def _knowledge_index_url(locale_code: str) -> str:
    index = live_page_in(KnowledgeIndexPage, Locale.objects.filter(language_code=locale_code).first())
    return index.url if index else "/"


class ManagerRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not roles.at_least(request.user, roles.MANAGE_KNOWLEDGE):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SubmitArticleView(ParticipantRequiredMixin, CreateView):
    model = DraftSubmission
    form_class = DraftSubmissionForm
    template_name = "knowledge/submit.html"
    success_url = reverse_lazy("account_profile")

    def get_initial(self):
        initial = super().get_initial()
        initial["locale"] = get_language() or settings.LANGUAGE_CODE
        return initial

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.submission_type = DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE
        return super().form_valid(form)


class AddArticleView(ManagerRequiredMixin, View):
    template_name = "knowledge/add_article.html"

    def get(self, request):
        form = KnowledgeArticleForm(initial={"locale": get_language() or settings.LANGUAGE_CODE})
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = KnowledgeArticleForm(request.POST)
        if form.is_valid():
            article = form.save(commit=False)
            article.published_by = request.user
            article.save()
            form.save_m2m()  # persist tags (commit=False skipped the M2M)
            return redirect(article.get_absolute_url())
        return render(request, self.template_name, {"form": form})


class EditArticleView(ManagerRequiredMixin, View):
    template_name = "knowledge/edit_article.html"

    def get(self, request, pk):
        article = get_object_or_404(KnowledgeArticle, pk=pk, is_deleted=False)
        form = KnowledgeArticleForm(instance=article)
        return render(request, self.template_name, {"form": form, "article": article})

    def post(self, request, pk):
        article = get_object_or_404(KnowledgeArticle, pk=pk, is_deleted=False)
        form = KnowledgeArticleForm(request.POST, instance=article)
        if form.is_valid():
            form.save()
            return redirect(article.get_absolute_url())
        return render(request, self.template_name, {"form": form, "article": article})


class SubmissionDetailView(ManagerRequiredMixin, View):
    def get(self, request, pk):
        submission = get_object_or_404(
            DraftSubmission,
            pk=pk,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
        )
        return render(request, "knowledge/submission_detail.html", {"submission": submission})


class ApproveSubmissionView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        submission = get_object_or_404(
            DraftSubmission,
            pk=pk,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
        )
        try:
            submission.approve(reviewer=request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("knowledge_submission_detail", pk=pk)
        messages.success(request, _("Article published successfully."))
        return redirect(_knowledge_index_url(submission.locale))


class RejectSubmissionView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        submission = get_object_or_404(
            DraftSubmission,
            pk=pk,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
        )
        note = request.POST.get("note", "")
        try:
            submission.reject(reviewer=request.user, note=note)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("knowledge_submission_detail", pk=pk)


class KnowledgeArticleDeleteView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        article = get_object_or_404(KnowledgeArticle, pk=pk, is_deleted=False)
        article.is_deleted = True
        article.save(update_fields=["is_deleted"])
        return redirect(_knowledge_index_url(article.locale))


class KnowledgeArticleHideView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        article = get_object_or_404(KnowledgeArticle, pk=pk, is_deleted=False)
        article.is_hidden = not article.is_hidden
        article.save(update_fields=["is_hidden"])
        return redirect(article.get_absolute_url())


class AddKnowledgeArticleCommentView(ParticipantRequiredMixin, View):
    def post(self, request, pk):
        can_manage = roles.at_least(request.user, roles.MANAGE_KNOWLEDGE)
        article = get_object_or_404(KnowledgeArticle, pk=pk, is_deleted=False)
        if article.is_hidden and not can_manage:
            raise Http404
        save_comment(request, AddKnowledgeArticleCommentForm(request.POST), article=article)
        return redirect(article.get_absolute_url())


class DeleteKnowledgeArticleCommentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not roles.at_least(request.user, roles.MANAGE_KNOWLEDGE):
            raise PermissionDenied
        comment = get_object_or_404(KnowledgeArticleComment.objects.select_related("article"), pk=pk)
        article_url = comment.article.get_absolute_url()
        comment.delete()
        return redirect(article_url)
