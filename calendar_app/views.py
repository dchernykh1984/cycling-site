import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView, TemplateView, View

from accounts.models import User
from locations.models import Location

from .forms import CompetitionFilterForm, RejectCompetitionForm, SubmitCompetitionForm
from .models import Competition, CyclingDiscipline, EventType


class ParticipantRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_superuser and request.user.get_role_rank() < User.ROLE_HIERARCHY.index(
            User.Role.PARTICIPANT
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class OrganizerRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_superuser and request.user.get_role_rank() < User.ROLE_HIERARCHY.index(
            User.Role.ORGANIZER
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class CalendarView(TemplateView):
    template_name = "calendar_app/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_types"] = EventType.objects.all()
        context["disciplines"] = CyclingDiscipline.objects.all()
        context["locations_data"] = list(Location.objects.order_by("path").values("pk", "depth", "path", "name_ru"))
        return context


class CalendarEventsAPIView(View):
    def get(self, request):
        from django.db.models import Q

        qs = Competition.objects.filter(status=Competition.Status.APPROVED).select_related("event_type", "discipline")
        start = (request.GET.get("start") or "")[:10]
        end = (request.GET.get("end") or "")[:10]
        if start and end:
            # Include multi-day events that overlap the visible range:
            # event starts before range end AND (has no end date but starts in range,
            # OR has end date that reaches into the range)
            qs = qs.filter(
                Q(date_start__lt=end) & (Q(date_end__gte=start) | Q(date_end__isnull=True, date_start__gte=start))
            )
        elif start:
            qs = qs.filter(Q(date_end__gte=start) | Q(date_end__isnull=True, date_start__gte=start))
        elif end:
            qs = qs.filter(date_start__lt=end)
        event_type_id = request.GET.get("event_type")
        discipline_id = request.GET.get("discipline")
        location_id = request.GET.get("location")
        if event_type_id:
            qs = qs.filter(event_type_id=event_type_id)
        if discipline_id:
            qs = qs.filter(discipline_id=discipline_id)
        if location_id:
            try:
                loc = Location.objects.get(pk=location_id)
                descendant_pks = loc.get_descendants(include_self=True).values_list("pk", flat=True)
                qs = qs.filter(location_id__in=descendant_pks)
            except Location.DoesNotExist:
                qs = qs.none()

        events = [
            {
                "id": comp.pk,
                "title": comp.title,
                "start": comp.date_start.isoformat(),
                "end": comp.get_calendar_end(),
                "url": reverse("competition_detail", args=[comp.pk]),
                "extendedProps": {
                    "event_type": comp.event_type.name if comp.event_type else "",
                    "discipline": comp.discipline.name if comp.discipline else "",
                },
            }
            for comp in qs
        ]
        return JsonResponse(events, safe=False)


class CompetitionListView(TemplateView):
    template_name = "calendar_app/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = CompetitionFilterForm(self.request.GET or None)
        today = timezone.localdate()
        date_from = today
        date_to = today + datetime.timedelta(days=30)

        qs = Competition.objects.filter(status=Competition.Status.APPROVED).select_related(
            "event_type", "discipline", "location"
        )

        if form.is_valid():
            if form.cleaned_data.get("event_type"):
                qs = qs.filter(event_type=form.cleaned_data["event_type"])
            if form.cleaned_data.get("discipline"):
                qs = qs.filter(discipline=form.cleaned_data["discipline"])
            if form.cleaned_data.get("location"):
                qs = qs.filter(location=form.cleaned_data["location"])
            if form.cleaned_data.get("date_from"):
                date_from = form.cleaned_data["date_from"]
            if form.cleaned_data.get("date_to"):
                date_to = form.cleaned_data["date_to"]

        qs = qs.filter(date_start__gte=date_from, date_start__lte=date_to).order_by("date_start")
        paginator = Paginator(qs, 20)
        context["competitions"] = paginator.get_page(self.request.GET.get("page", 1))
        context["filter_form"] = form
        context["date_from"] = date_from
        context["date_to"] = date_to
        return context


class CompetitionDetailView(View):
    def get(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, status=Competition.Status.APPROVED)
        protocols = competition.protocols.all()
        show_upload_token = request.user.is_authenticated and (
            request.user.is_superuser
            or request.user == competition.submitted_by
            or request.user.get_role_rank() >= User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)
        )
        return render(
            request,
            "calendar_app/detail.html",
            {
                "competition": competition,
                "protocols": protocols,
                "show_upload_token": show_upload_token,
            },
        )


class SubmitCompetitionView(ParticipantRequiredMixin, FormView):
    template_name = "calendar_app/submit.html"
    form_class = SubmitCompetitionForm

    def form_valid(self, form):
        cd = form.cleaned_data
        is_organizer = self.request.user.is_superuser or self.request.user.get_role_rank() >= User.ROLE_HIERARCHY.index(
            User.Role.ORGANIZER
        )

        comp = Competition(
            title_ru=cd["title"],
            description_ru=cd.get("description", ""),
            event_type=cd.get("event_type"),
            discipline=cd.get("discipline"),
            location=cd.get("location"),
            date_start=cd["date_start"],
            date_end=cd.get("date_end"),
            url_announcement=cd.get("url_announcement", ""),
            url_registration=cd.get("url_registration", ""),
            url_route=cd.get("url_route", ""),
            url_regulations=cd.get("url_regulations", ""),
            url_results=cd.get("url_results", ""),
            submitted_by=self.request.user,
        )
        if is_organizer:
            comp.status = Competition.Status.APPROVED
            comp.approved_by = self.request.user
            comp.approved_at = timezone.now()
        else:
            comp.status = Competition.Status.PENDING_APPROVAL
        comp.save()
        return redirect("calendar_list")


class ModerationView(OrganizerRequiredMixin, TemplateView):
    template_name = "calendar_app/moderate.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["competitions"] = (
            Competition.objects.filter(status=Competition.Status.PENDING_APPROVAL)
            .select_related("submitted_by", "event_type", "discipline", "location")
            .order_by("date_start")
        )
        context["reject_form"] = RejectCompetitionForm()
        return context


class ApproveCompetitionView(OrganizerRequiredMixin, View):
    def post(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk, status=Competition.Status.PENDING_APPROVAL)
        comp.approve(reviewer=request.user)
        return redirect("calendar_moderate")


class RejectCompetitionView(OrganizerRequiredMixin, View):
    def post(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk, status=Competition.Status.PENDING_APPROVAL)
        form = RejectCompetitionForm(request.POST)
        reason = ""
        if form.is_valid():
            reason = form.cleaned_data.get("rejection_reason", "")
        try:
            comp.reject(reviewer=request.user, reason=reason)
        except ValueError:
            pass
        return redirect("calendar_moderate")
