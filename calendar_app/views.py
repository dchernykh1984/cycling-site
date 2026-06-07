import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import User
from locations.models import Location

from .forms import CompetitionFilterForm, RegistrationSettingsForm, RejectCompetitionForm, SubmitCompetitionForm
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
        from registrations.views import can_manage

        is_manager = can_manage(request.user, competition)
        already_registered = False
        if request.user.is_authenticated and competition.registration_mode == "self_only":
            from registrations.models import CompetitionRegistration

            already_registered = CompetitionRegistration.objects.filter(
                competition=competition, user=request.user
            ).exists()
        from django.conf import settings

        return render(
            request,
            "calendar_app/detail.html",
            {
                "competition": competition,
                "protocols": protocols,
                "show_upload_token": show_upload_token,
                "is_manager": is_manager,
                "already_registered": already_registered,
                "site_base_url": getattr(settings, "SITE_BASE_URL", ""),
            },
        )


def _validate_deadline(form, reg_form, date_start, date_end):
    """Add error to reg_form if registration_deadline exceeds the competition end date."""
    deadline = reg_form.cleaned_data.get("registration_deadline")
    if not deadline:
        return True
    max_date = date_end if date_end else date_start
    if deadline > max_date:
        label = "date end" if date_end else "date start"
        reg_form.add_error(
            "registration_deadline",
            f"Registration deadline cannot be later than the competition {label}.",
        )
        return False
    return True


def _apply_registration_settings(comp, reg_form, is_organizer_plus):
    if not is_organizer_plus:
        comp.registration_enabled = False
        return
    cd = reg_form.cleaned_data
    reg_enabled = cd.get("registration_enabled", False)
    comp.registration_enabled = reg_enabled
    if not comp.registration_mode_locked:
        comp.registration_mode = cd.get("registration_mode") or Competition.RegistrationMode.SELF_ONLY
    comp.birth_date_mode = cd.get("birth_date_mode") or Competition.BirthDateMode.YEAR
    comp.require_approval = cd.get("require_approval", False)
    comp.require_payment = cd.get("require_payment", False)
    effective_mode = comp.registration_mode if comp.registration_mode_locked else cd.get("registration_mode")
    comp.allow_multiple_registrations = (
        False if effective_mode == "self_only" else cd.get("allow_multiple_registrations", False)
    )
    comp.registration_deadline = cd.get("registration_deadline")
    comp.max_participants = cd.get("max_participants")
    comp.show_unapproved_in_list = cd.get("show_unapproved_in_list", False) if comp.require_approval else False
    comp.show_unpaid_in_list = cd.get("show_unpaid_in_list", False) if comp.require_payment else False
    comp.show_approval_status_col = cd.get("show_approval_status_col", False) if comp.require_approval else False
    comp.show_payment_status_col = cd.get("show_payment_status_col", False) if comp.require_payment else False
    comp.show_additional_info_field = cd.get("show_additional_info_field", True)
    if reg_enabled and not comp.registration_mode_locked:
        comp.registration_mode_locked = True


def _save_categories(comp, reg_form):  # noqa: C901
    import datetime as dt

    from registrations.models import RegistrationCategory

    cats = reg_form.get_categories()
    for cat_data in cats:
        cat_id = cat_data.get("id")
        is_del = cat_data.get("is_deleted", False)
        birth_date_mode = comp.birth_date_mode
        birth_from = None
        birth_to = None
        if cat_data.get("birth_from"):
            try:
                if birth_date_mode == "year":
                    birth_from = dt.date(int(cat_data["birth_from"]), 1, 1)
                else:
                    birth_from = dt.date.fromisoformat(cat_data["birth_from"])
            except (ValueError, TypeError):
                pass
        if cat_data.get("birth_to"):
            try:
                if birth_date_mode == "year":
                    birth_to = dt.date(int(cat_data["birth_to"]), 12, 31)
                else:
                    birth_to = dt.date.fromisoformat(cat_data["birth_to"])
            except (ValueError, TypeError):
                pass

        if cat_id and str(cat_id).isdigit():
            try:
                cat = RegistrationCategory.objects.get(pk=cat_id, competition=comp)
                if is_del:
                    cat.is_deleted = True
                    cat.save(update_fields=["is_deleted"])
                    continue
                cat.name = cat_data.get("name", cat.name)
                cat.male = cat_data.get("male", True)
                cat.female = cat_data.get("female", True)
                cat.birth_from = birth_from
                cat.birth_to = birth_to
                cat.laps = cat_data.get("laps") or None
                cat.bib_from = cat_data.get("bib_from") or None
                cat.bib_to = cat_data.get("bib_to") or None
                cat.max_participants = cat_data.get("max_participants") or None
                cat.save()
            except RegistrationCategory.DoesNotExist:
                pass
        else:
            if is_del:
                continue
            name = cat_data.get("name", "").strip()
            if not name:
                continue
            RegistrationCategory.objects.create(
                competition=comp,
                name=name,
                male=cat_data.get("male", True),
                female=cat_data.get("female", True),
                birth_from=birth_from,
                birth_to=birth_to,
                laps=cat_data.get("laps") or None,
                bib_from=cat_data.get("bib_from") or None,
                bib_to=cat_data.get("bib_to") or None,
                max_participants=cat_data.get("max_participants") or None,
            )


class SubmitCompetitionView(ParticipantRequiredMixin, View):
    template_name = "calendar_app/submit.html"

    def _is_organizer_plus(self, user):
        return user.is_superuser or user.get_role_rank() >= User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)

    def get(self, request):
        form = SubmitCompetitionForm()
        reg_form = RegistrationSettingsForm()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "reg_form": reg_form,
                "is_organizer_plus": self._is_organizer_plus(request.user),
            },
        )

    def post(self, request):
        form = SubmitCompetitionForm(request.POST)
        reg_form = RegistrationSettingsForm(request.POST)
        is_organizer = self._is_organizer_plus(request.user)
        if form.is_valid() and (not is_organizer or reg_form.is_valid()):
            cd = form.cleaned_data
            if is_organizer and not _validate_deadline(form, reg_form, cd["date_start"], cd.get("date_end")):
                return render(
                    request,
                    self.template_name,
                    {"form": form, "reg_form": reg_form, "is_organizer_plus": is_organizer},
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
                submitted_by=request.user,
            )
            if is_organizer:
                comp.status = Competition.Status.APPROVED
                comp.approved_by = request.user
                comp.approved_at = timezone.now()
            else:
                comp.status = Competition.Status.PENDING_APPROVAL
            if is_organizer:
                _apply_registration_settings(comp, reg_form, True)
            else:
                comp.registration_enabled = False
            comp.save()
            if is_organizer and reg_form.is_valid():
                _save_categories(comp, reg_form)
            return redirect("calendar_list")
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "reg_form": reg_form,
                "is_organizer_plus": is_organizer,
            },
        )


class EditCompetitionView(View):
    template_name = "calendar_app/edit.html"

    def _get_competition_or_403(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk)
        from registrations.views import can_manage

        if not can_manage(request.user, comp):
            raise PermissionDenied
        return comp

    def get(self, request, pk):
        comp = self._get_competition_or_403(request, pk)
        form = SubmitCompetitionForm(
            initial={
                "title": comp.title,
                "description": comp.description,
                "event_type": comp.event_type_id,
                "discipline": comp.discipline_id,
                "location": comp.location_id,
                "date_start": comp.date_start,
                "date_end": comp.date_end,
                "url_announcement": comp.url_announcement,
                "url_registration": comp.url_registration,
                "url_route": comp.url_route,
                "url_regulations": comp.url_regulations,
                "url_results": comp.url_results,
            }
        )
        reg_form = RegistrationSettingsForm(
            initial={
                "registration_enabled": comp.registration_enabled,
                "registration_mode": comp.registration_mode,
                "birth_date_mode": comp.birth_date_mode,
                "require_approval": comp.require_approval,
                "require_payment": comp.require_payment,
                "allow_multiple_registrations": comp.allow_multiple_registrations,
                "registration_deadline": comp.registration_deadline,
                "max_participants": comp.max_participants,
                "show_unapproved_in_list": comp.show_unapproved_in_list,
                "show_unpaid_in_list": comp.show_unpaid_in_list,
                "show_approval_status_col": comp.show_approval_status_col,
                "show_payment_status_col": comp.show_payment_status_col,
                "show_additional_info_field": comp.show_additional_info_field,
            }
        )
        import json

        from registrations.models import RegistrationCategory

        categories = list(
            RegistrationCategory.objects.filter(competition=comp, is_deleted=False).values(
                "id",
                "name",
                "male",
                "female",
                "birth_from",
                "birth_to",
                "laps",
                "bib_from",
                "bib_to",
                "max_participants",
            )
        )
        for c in categories:
            if c["birth_from"]:
                c["birth_from"] = (
                    c["birth_from"].isoformat() if comp.birth_date_mode == "date" else str(c["birth_from"].year)
                )
            if c["birth_to"]:
                c["birth_to"] = c["birth_to"].isoformat() if comp.birth_date_mode == "date" else str(c["birth_to"].year)
        return render(
            request,
            self.template_name,
            {
                "competition": comp,
                "form": form,
                "reg_form": reg_form,
                "categories_json": json.dumps(categories),
                "mode_locked": comp.registration_mode_locked,
            },
        )

    def post(self, request, pk):
        comp = self._get_competition_or_403(request, pk)
        form = SubmitCompetitionForm(request.POST)
        reg_form = RegistrationSettingsForm(request.POST)
        if form.is_valid() and reg_form.is_valid():
            cd = form.cleaned_data
            if not _validate_deadline(form, reg_form, cd["date_start"], cd.get("date_end")):
                import json as _json

                from registrations.models import RegistrationCategory

                _cats = list(
                    RegistrationCategory.objects.filter(competition=comp, is_deleted=False).values(
                        "id",
                        "name",
                        "male",
                        "female",
                        "birth_from",
                        "birth_to",
                        "laps",
                        "bib_from",
                        "bib_to",
                        "max_participants",
                    )
                )
                _birth_mode = reg_form.cleaned_data.get("birth_date_mode") or comp.birth_date_mode
                for _c in _cats:
                    if _c["birth_from"]:
                        _c["birth_from"] = (
                            _c["birth_from"].isoformat() if _birth_mode == "date" else str(_c["birth_from"].year)
                        )
                    if _c["birth_to"]:
                        _c["birth_to"] = (
                            _c["birth_to"].isoformat() if _birth_mode == "date" else str(_c["birth_to"].year)
                        )
                return render(
                    request,
                    self.template_name,
                    {
                        "competition": comp,
                        "form": form,
                        "reg_form": reg_form,
                        "categories_json": _json.dumps(_cats),
                        "mode_locked": comp.registration_mode_locked,
                    },
                )
            comp.title_ru = cd["title"]
            comp.description_ru = cd.get("description", "")
            comp.event_type = cd.get("event_type")
            comp.discipline = cd.get("discipline")
            comp.location = cd.get("location")
            comp.date_start = cd["date_start"]
            comp.date_end = cd.get("date_end")
            comp.url_announcement = cd.get("url_announcement", "")
            comp.url_registration = cd.get("url_registration", "")
            comp.url_route = cd.get("url_route", "")
            comp.url_regulations = cd.get("url_regulations", "")
            comp.url_results = cd.get("url_results", "")
            _apply_registration_settings(comp, reg_form, True)
            comp.save()
            _save_categories(comp, reg_form)
            return redirect("competition_detail", pk=comp.pk)
        import json

        from registrations.models import RegistrationCategory

        categories = list(
            RegistrationCategory.objects.filter(competition=comp, is_deleted=False).values(
                "id",
                "name",
                "male",
                "female",
                "birth_from",
                "birth_to",
                "laps",
                "bib_from",
                "bib_to",
                "max_participants",
            )
        )
        return render(
            request,
            self.template_name,
            {
                "competition": comp,
                "form": form,
                "reg_form": reg_form,
                "categories_json": json.dumps(categories, default=str),
                "mode_locked": comp.registration_mode_locked,
            },
        )


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
