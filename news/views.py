from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import get_language, gettext
from django.views.generic import CreateView, View

from accounts.models import User
from knowledge.models import DraftSubmission
from news.forms import AddCommentForm, AddNewsArticleCommentForm, NewsArticleForm, SubmitNewsForm
from news.models import Comment, NewsArticle, NewsArticleComment, NewsPage, NewsSettings

_PARTICIPANT_RANK = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)


def _can_comment(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _PARTICIPANT_RANK)


_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def _can_manage_news(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


class NewsListView(View):
    def get(self, request):
        can_manage = _can_manage_news(request.user)
        qs = NewsArticle.objects.filter(is_deleted=False)
        if not can_manage:
            qs = qs.filter(is_hidden=False)
        paginator = Paginator(qs, 12)
        news_items = paginator.get_page(request.GET.get("page", 1))

        context = {"news_items": news_items, "can_add": can_manage}
        if can_manage:
            context["pending_submissions"] = (
                DraftSubmission.objects.filter(
                    status=DraftSubmission.Status.PENDING,
                    submission_type=DraftSubmission.SubmissionType.NEWS,
                )
                .select_related("author")
                .order_by("submitted_at")
            )
        return render(request, "news/news_list.html", context)


class NewsArticleDetailView(View):
    def get(self, request, pk):
        can_manage = _can_manage_news(request.user)
        article = get_object_or_404(NewsArticle, pk=pk, is_deleted=False)
        if article.is_deleted or (article.is_hidden and not can_manage):
            raise Http404
        can_comment = _can_comment(request.user)
        return render(
            request,
            "news/article_detail.html",
            {
                "article": article,
                "can_edit": can_manage,
                "comments": article.comments.select_related("author"),
                "can_comment": can_comment,
                "comment_form": AddNewsArticleCommentForm() if can_comment else None,
                "user_can_delete_comment": can_manage,
            },
        )


class NewsArticleDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        article = get_object_or_404(NewsArticle, pk=pk, is_deleted=False)
        article.is_deleted = True
        article.save(update_fields=["is_deleted"])
        return redirect("news_index")


class NewsArticleHideView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        article = get_object_or_404(NewsArticle, pk=pk, is_deleted=False)
        article.is_hidden = not article.is_hidden
        article.save(update_fields=["is_hidden"])
        return redirect("news_article_detail", pk=pk)


class NewsArticleCreateView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        now = timezone.localtime(timezone.now())
        form = NewsArticleForm(initial={"published_at": now.strftime("%Y-%m-%dT%H:%M")})
        return render(request, "news/article_form.html", {"form": form, "action": "create"})

    def post(self, request):
        form = NewsArticleForm(request.POST, request.FILES)
        if form.is_valid():
            article = form.save(commit=False)
            article.published_by = request.user
            article.save()
            return redirect(article.get_absolute_url())
        return render(request, "news/article_form.html", {"form": form, "action": "create"})


class NewsArticleEditView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        article = get_object_or_404(NewsArticle, pk=pk, is_deleted=False)
        form = NewsArticleForm(instance=article)
        return render(request, "news/article_form.html", {"form": form, "article": article, "action": "edit"})

    def post(self, request, pk):
        article = get_object_or_404(NewsArticle, pk=pk, is_deleted=False)
        form = NewsArticleForm(request.POST, request.FILES, instance=article)
        if form.is_valid():
            form.save()
            return redirect(article.get_absolute_url())
        return render(request, "news/article_form.html", {"form": form, "article": article, "action": "edit"})


class ParticipantRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
        # Superusers bypass the role gate, matching the comment-form display check (_can_comment)
        # so they don't see the form via GET only to be rejected on POST.
        if not request.user.is_superuser and request.user.get_role_rank() < participant_rank:
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


class NewsSubmissionApproveView(LoginRequiredMixin, View):
    """Publish a pending news submission straight from the news index (manager+ only)."""

    def post(self, request, pk):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        submission = get_object_or_404(DraftSubmission, pk=pk, submission_type=DraftSubmission.SubmissionType.NEWS)
        try:
            submission.approve(reviewer=request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("news_index")
        messages.success(request, gettext("News published successfully."))
        return redirect("news_index")


class NewsSubmissionRejectView(LoginRequiredMixin, View):
    """Reject a pending news submission from the news index (manager+ only)."""

    def post(self, request, pk):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        submission = get_object_or_404(DraftSubmission, pk=pk, submission_type=DraftSubmission.SubmissionType.NEWS)
        try:
            submission.reject(reviewer=request.user, note=request.POST.get("note", ""))
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("news_index")


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
        if not _can_manage_news(request.user):
            raise PermissionDenied
        comment = get_object_or_404(Comment, pk=pk)
        page_url = comment.page.url
        comment.delete()
        return redirect(page_url)


class AddNewsArticleCommentView(ParticipantRequiredMixin, View):
    def post(self, request, pk):
        can_manage = _can_manage_news(request.user)
        article = get_object_or_404(NewsArticle, pk=pk, is_deleted=False)
        if article.is_hidden and not can_manage:
            raise Http404
        form = AddNewsArticleCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.article = article
            comment.author = request.user
            comment.save()
        else:
            first_errors = next(iter(form.errors.values()), [])
            messages.error(request, first_errors[0] if first_errors else gettext("Invalid submission."))
        return redirect("news_article_detail", pk=pk)


class DeleteNewsArticleCommentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not _can_manage_news(request.user):
            raise PermissionDenied
        comment = get_object_or_404(NewsArticleComment, pk=pk)
        article_pk = comment.article_id
        comment.delete()
        return redirect("news_article_detail", pk=article_pk)
