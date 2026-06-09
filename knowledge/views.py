from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import get_language
from django.views.generic import CreateView, View

from accounts.models import User
from knowledge.forms import DraftSubmissionForm
from knowledge.models import DraftSubmission, KnowledgeArticlePage

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
