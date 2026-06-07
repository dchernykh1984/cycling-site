from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import get_language
from django.views.generic import CreateView, View

from accounts.models import User
from knowledge.models import DraftSubmission
from news.forms import AddCommentForm, SubmitNewsForm
from news.models import Comment, NewsPage, NewsSettings


class ParticipantRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
        if request.user.get_role_rank() < participant_rank:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SubmitNewsView(ParticipantRequiredMixin, CreateView):
    model = DraftSubmission
    form_class = SubmitNewsForm
    template_name = "news/submit.html"
    success_url = reverse_lazy("account_profile")

    def get_initial(self):
        initial = super().get_initial()
        initial["locale"] = get_language() or "ru"
        return initial

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.submission_type = DraftSubmission.SubmissionType.NEWS
        return super().form_valid(form)


class AddCommentView(ParticipantRequiredMixin, View):
    def post(self, request, page_pk):
        page = get_object_or_404(NewsPage.objects.live(), pk=page_pk)
        form = AddCommentForm(request.POST)
        if form.is_valid():
            settings = NewsSettings.load(request_or_site=request)
            comment = form.save(commit=False)
            comment.page = page
            comment.author = request.user
            comment.is_approved = settings.auto_approve_comments
            comment.save()
        return redirect(page.url)


class DeleteCommentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied
        comment = get_object_or_404(Comment, pk=pk)
        page_url = comment.page.url
        comment.delete()
        return redirect(page_url)
