from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.utils.translation import get_language
from django.views.generic import CreateView

from accounts.models import User
from knowledge.forms import DraftSubmissionForm
from knowledge.models import DraftSubmission


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
