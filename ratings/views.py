"""The pages of the ratings (issue #436): the organizers' ratings, and a participant's review of an event."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.views import View
from django.views.generic import TemplateView

from assistant import llm
from calendar_app.models import Competition
from calendar_app.visibility import can_manage_or_own
from ratings import digest, form, rules, scores


def _back(request, competition) -> str:
    """Where to go after answering: the page the request came from, else the event's page."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    safe = url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return target if safe else competition.get_absolute_url()


class ReviewView(LoginRequiredMixin, View):
    """A participant's review of an event they took part in, or their refusal to give one: either is
    the answer, once. A member who may not review it, or answered already, finds no page."""

    template_name = "ratings/review.html"

    def _page(self, request, competition, raw=None, errors=None):
        raw = raw or {}
        rows = [
            {"question": question, "value": raw.get(question.key, ""), "error": (errors or {}).get(question.key)}
            for question in form.QUESTIONS
        ]
        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "rows": rows,
                "score": form.SCORE,
                "scores": range(form.LOWEST, form.HIGHEST + 1),
                "text_length": form.TEXT_LENGTH,
                "next": _back(request, competition),
                # The page is the request itself: the banner's answers would come back to a page gone
                "review_requests": [],
            },
        )

    def get(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk)
        if not rules.reviewable(request.user, competition):
            raise Http404
        return self._page(request, competition)

    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk)
        target = _back(request, competition)
        if "decline" in request.POST:
            if rules.answer(request.user, competition):
                messages.info(request, gettext("We will not ask about this event again."))
            return redirect(target)
        answers, errors = form.clean(request.POST)
        if errors:
            if not rules.reviewable(request.user, competition):
                raise Http404
            return self._page(request, competition, request.POST, errors)
        if rules.answer(request.user, competition, answers):
            messages.success(request, gettext("Thank you! Nobody will know the review is yours."))
        else:
            messages.error(request, gettext("This event cannot be rated, or you have answered already."))
        return redirect(target)


class RatingsView(TemplateView):
    """The Ratings tab: the organizers rated by the participants of their events, the best first."""

    template_name = "ratings/index.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            organizers=scores.organizers(), public_from=scores.PUBLIC_FROM, meta_title=gettext("Ratings"), **kwargs
        )


class SummaryView(LoginRequiredMixin, View):
    """What the participants think of an event, for the people who edit it -- its author, the admins and
    the owners: the figures, and the digest the language model writes by a button. Anybody else finds no
    page."""

    template_name = "ratings/summary.html"

    def _event(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk)
        if not can_manage_or_own(request.user, competition):
            raise Http404
        return competition

    def get(self, request, pk):
        competition = self._event(request, pk)
        figures = digest.figures(competition)
        summary = digest.kept(competition) if figures["shown"] else None
        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "figures": figures,
                "summary": summary,
                "outdated": figures["shown"] and (summary is None or summary.reviews < figures["reviews"]),
                "digest_from": digest.DIGEST_FROM,
            },
        )

    def post(self, request, pk):
        competition = self._event(request, pk)
        try:
            digest.write(competition)
        except ValueError:
            pass  # too few reviews: the page says so
        except llm.UnavailableError:
            messages.error(
                request,
                gettext("The digest could not be written now: the language model did not answer. Try again later."),
            )
        return redirect("ratings:summary", pk=competition.pk)
