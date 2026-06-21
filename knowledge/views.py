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

from accounts.models import User
from knowledge.forms import AddKnowledgeArticleCommentForm, DraftSubmissionForm, KnowledgeArticleForm
from knowledge.models import DraftSubmission, KnowledgeArticle, KnowledgeArticleComment, KnowledgeIndexPage

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def _can_manage_knowledge(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


def _knowledge_index_url(locale_code: str) -> str:
    loc = Locale.objects.filter(language_code=locale_code).first()
    index = KnowledgeIndexPage.objects.live().filter(locale=loc).first() if loc else None
    if index is None:
        index = KnowledgeIndexPage.objects.live().first()
    return index.url if index else "/"


class ParticipantRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
        # Superusers bypass the role gate, matching the comment-form display check so they don't
        # see the form via GET only to be rejected on POST.
        if not request.user.is_superuser and request.user.get_role_rank() < participant_rank:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ManagerRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not _can_manage_knowledge(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SubmitArticleView(ParticipantRequiredMixin, CreateView):
    model = DraftSubmission
    form_class = DraftSubmissionForm
    template_name = "knowledge/submit.html"
    success_url = reverse_lazy("account_profile")

    def get_initial(self):
        initial = super().get_initial()
        initial["locale"] = get_language() or "ru"
        return initial

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.submission_type = DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE
        return super().form_valid(form)


class AddArticleView(ManagerRequiredMixin, View):
    template_name = "knowledge/add_article.html"

    def get(self, request):
        form = KnowledgeArticleForm(initial={"locale": get_language() or "ru"})
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
        can_manage = _can_manage_knowledge(request.user)
        article = get_object_or_404(KnowledgeArticle, pk=pk, is_deleted=False)
        if article.is_hidden and not can_manage:
            raise Http404
        form = AddKnowledgeArticleCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.article = article
            comment.author = request.user
            comment.save()
        else:
            first_errors = next(iter(form.errors.values()), [])
            messages.error(request, first_errors[0] if first_errors else _("Invalid submission."))
        return redirect(article.get_absolute_url())


class DeleteKnowledgeArticleCommentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not _can_manage_knowledge(request.user):
            raise PermissionDenied
        comment = get_object_or_404(KnowledgeArticleComment.objects.select_related("article"), pk=pk)
        article_url = comment.article.get_absolute_url()
        comment.delete()
        return redirect(article_url)
