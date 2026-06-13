from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import get_language
from django.views.generic import CreateView, View
from wagtail.models import Locale

from accounts.models import User
from knowledge.forms import DraftSubmissionForm
from knowledge.models import DraftSubmission, KnowledgeArticlePage, KnowledgeIndexPage

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def _can_manage_knowledge(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


class ParticipantRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
        if request.user.get_role_rank() < participant_rank:
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


class AddArticleView(ManagerRequiredMixin, CreateView):
    model = DraftSubmission
    form_class = DraftSubmissionForm
    template_name = "knowledge/add_article.html"

    def get_initial(self):
        initial = super().get_initial()
        initial["locale"] = get_language() or "ru"
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lang = get_language() or "ru"
        locale = Locale.objects.filter(language_code=lang).first()
        if locale:
            index = KnowledgeIndexPage.objects.live().filter(locale=locale).first()
            if index:
                ctx["index_url"] = index.url
        return ctx

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.submission_type = DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE
        submission = form.save()
        try:
            submission.approve(reviewer=self.request.user)
        except ValueError as e:
            submission.delete()
            form.add_error(None, str(e))
            return self.form_invalid(form)
        locale = Locale.objects.filter(language_code=submission.locale).first()
        if locale:
            index = KnowledgeIndexPage.objects.live().filter(locale=locale).first()
            if index:
                return redirect(index.url)
        return redirect("/")


class SubmissionDetailView(ManagerRequiredMixin, View):
    def get(self, request, pk):
        submission = get_object_or_404(DraftSubmission, pk=pk)
        return render(request, "knowledge/submission_detail.html", {"submission": submission})


class ApproveSubmissionView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        submission = get_object_or_404(DraftSubmission, pk=pk)
        try:
            submission.approve(reviewer=request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("knowledge_submission_detail", pk=pk)
        locale = Locale.objects.filter(language_code=submission.locale).first()
        if locale:
            index = KnowledgeIndexPage.objects.live().filter(locale=locale).first()
            if index:
                return redirect(index.url)
        return redirect("/")


class RejectSubmissionView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        submission = get_object_or_404(DraftSubmission, pk=pk)
        note = request.POST.get("note", "")
        try:
            submission.reject(reviewer=request.user, note=note)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("knowledge_submission_detail", pk=pk)


class KnowledgeArticleDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not _can_manage_knowledge(request.user):
            raise PermissionDenied
        article = get_object_or_404(KnowledgeArticlePage, pk=pk, is_deleted=False)
        article.is_deleted = True
        article.save(update_fields=["is_deleted"])
        parent = article.get_parent()
        return redirect(parent.url if parent else "/")


class KnowledgeArticleHideView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not _can_manage_knowledge(request.user):
            raise PermissionDenied
        article = get_object_or_404(KnowledgeArticlePage, pk=pk, is_deleted=False)
        article.is_hidden = not article.is_hidden
        article.save(update_fields=["is_hidden"])
        return redirect(article.url)
