import csv
import datetime
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User
from calendar_app.models import Competition

from .forms import EditRegistrationForm, RegistrationForm
from .models import CompetitionRegistration, RegistrationCategory, Team, check_duplicate


def can_manage(user, competition) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    rank = user.get_role_rank()
    if rank >= User.ROLE_HIERARCHY.index(User.Role.ADMIN):
        return True
    if rank >= User.ROLE_HIERARCHY.index(User.Role.ORGANIZER):
        return user == competition.submitted_by
    return False


class RegisterForCompetitionView(LoginRequiredMixin, View):
    template_name = "registrations/register.html"

    def _get_competition(self, pk):
        return get_object_or_404(Competition, pk=pk, is_deleted=False)

    def _check_participant(self, request):
        if not request.user.is_superuser and request.user.get_role_rank() < User.ROLE_HIERARCHY.index(
            User.Role.PARTICIPANT
        ):
            raise PermissionDenied

    def _available_categories(self, competition, gender, birth_date):
        qs = RegistrationCategory.objects.filter(competition=competition, is_deleted=False)
        if gender and birth_date:
            qs = [c for c in qs if c.matches(gender, birth_date) and c.is_open()]
        else:
            qs = []
        return qs

    def get(self, request, pk):
        self._check_participant(request)
        competition = self._get_competition(pk)
        if competition.is_hidden and not can_manage(request.user, competition):
            raise Http404
        if not competition.is_registration_open():
            return render(
                request,
                self.template_name,
                {
                    "competition": competition,
                    "registration_closed": True,
                },
            )

        user = request.user
        is_free = competition.registration_mode == "free"
        readonly_fields = [] if is_free else ["first_name", "last_name", "birth_date", "birth_year", "gender"]

        profile_incomplete = not user.gender or not user.birth_date

        if is_free:
            gender = user.gender or ""
            birth_date = user.birth_date
        else:
            gender = user.gender
            birth_date = user.birth_date

        available_categories = (
            self._available_categories(competition, gender, birth_date) if (gender and birth_date) else []
        )

        initial = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "gender": gender,
        }
        if competition.birth_date_mode == "year":
            initial["birth_year"] = birth_date.year if birth_date else None
        else:
            initial["birth_date"] = birth_date
        if available_categories:
            initial["category"] = available_categories[0].pk

        form = RegistrationForm(initial=initial, competition=competition, user=user, readonly_fields=readonly_fields)
        form.fields["category"].queryset = RegistrationCategory.objects.filter(
            pk__in=[c.pk for c in available_categories]
        )

        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "form": form,
                "profile_incomplete": profile_incomplete,
                "is_free": is_free,
                "relay_enabled": competition.relay_enabled,
                "relay_max_members": competition.relay_max_members,
                "available_categories_json": json.dumps([{"id": c.pk, "name": c.name} for c in available_categories]),
                "all_categories_json": json.dumps(
                    [
                        {
                            "id": c.pk,
                            "name": c.name,
                            "male": c.male,
                            "female": c.female,
                            "birth_from": c.birth_from.isoformat() if c.birth_from else None,
                            "birth_to": c.birth_to.isoformat() if c.birth_to else None,
                            "is_open": c.is_open(),
                        }
                        for c in RegistrationCategory.objects.filter(competition=competition, is_deleted=False)
                    ]
                ),
            },
        )

    def post(self, request, pk):  # noqa: C901
        self._check_participant(request)
        competition = self._get_competition(pk)
        if competition.is_hidden and not can_manage(request.user, competition):
            raise Http404
        if not competition.is_registration_open():
            raise PermissionDenied

        user = request.user
        is_free = competition.registration_mode == "free"
        readonly_fields = [] if is_free else ["first_name", "last_name", "birth_date", "birth_year", "gender"]

        if not is_free:
            if not user.gender or not user.birth_date:
                raise PermissionDenied

        form = RegistrationForm(request.POST, competition=competition, user=user, readonly_fields=readonly_fields)
        form.fields["category"].queryset = RegistrationCategory.objects.filter(
            competition=competition, is_deleted=False
        )

        relay_enabled = competition.relay_enabled
        relay_names = []
        relay_birth_years = []
        relay_cities = []
        if relay_enabled:
            relay_names = [n.strip() for n in request.POST.getlist("participant_name") if n.strip()]
            relay_birth_years = [y.strip() for y in request.POST.getlist("participant_birth_year")]
            relay_cities = [c.strip() for c in request.POST.getlist("participant_city")]
            # Pad / trim auxiliary lists to match names length
            relay_birth_years = (relay_birth_years + [""] * len(relay_names))[: len(relay_names)]
            relay_cities = (relay_cities + [""] * len(relay_names))[: len(relay_names)]
            if not relay_names:
                form.add_error(None, "At least one participant name is required.")
            elif len(relay_names) > competition.relay_max_members:
                form.add_error(None, f"Maximum {competition.relay_max_members} members allowed.")

        if form.is_valid() and not form.errors:
            cleaned = form.cleaned_data

            if not is_free:
                first_name = user.first_name
                last_name = user.last_name
                gender = user.gender
                birth_date = user.birth_date
            else:
                first_name = "" if relay_enabled else cleaned["first_name"]
                last_name = "" if relay_enabled else cleaned["last_name"]
                gender = cleaned["gender"]
                if relay_enabled and relay_birth_years:
                    try:
                        birth_date = datetime.date(int(relay_birth_years[0]), 1, 1)
                    except (ValueError, TypeError):
                        birth_date = datetime.date(1900, 1, 1)
                else:
                    birth_date = cleaned.get("birth_date") or (
                        datetime.date(cleaned["birth_year"], 1, 1)
                        if cleaned.get("birth_year")
                        else datetime.date(1900, 1, 1)
                    )

            if not relay_enabled and check_duplicate(competition, user, first_name, last_name, birth_date):
                form.add_error(None, "You are already registered for this competition.")
                return render(
                    request,
                    self.template_name,
                    {
                        "competition": competition,
                        "form": form,
                        "is_free": is_free,
                        "relay_enabled": relay_enabled,
                        "relay_max_members": competition.relay_max_members,
                    },
                )

            team = None
            team_name = cleaned.get("team_name", "").strip()
            if team_name:
                team = Team.get_or_restore(team_name)

            category = cleaned.get("category")
            # For relay only check gender; birth years span multiple age groups
            cat_ok = not category or (
                category.is_open()
                and (category.matches_gender(gender) if relay_enabled else category.matches(gender, birth_date))
            )
            if not cat_ok:
                form.add_error("category", "This category is not available.")
                return render(
                    request,
                    self.template_name,
                    {
                        "competition": competition,
                        "form": form,
                        "is_free": is_free,
                        "relay_enabled": relay_enabled,
                        "relay_max_members": competition.relay_max_members,
                    },
                )

            CompetitionRegistration.objects.create(
                competition=competition,
                user=user if competition.registration_mode == "self_only" else None,
                registered_by=user,
                first_name=first_name,
                last_name=last_name,
                participant_names="<BR>".join(relay_names) if relay_enabled else "",
                participant_birth_years="<BR>".join(relay_birth_years) if relay_enabled else "",
                participant_cities="<BR>".join(relay_cities) if relay_enabled else "",
                birth_date=birth_date,
                gender=gender,
                category=category,
                city="" if relay_enabled else cleaned.get("city", ""),
                team=team,
                additional_info=cleaned.get("additional_info", ""),
            )

            Competition.objects.filter(pk=competition.pk, registration_mode_locked=False).update(
                registration_mode_locked=True
            )

            return redirect("registrations:participant_list", pk=competition.pk)

        relay_members_post = [
            {"name": n, "birth_year": y, "city": c}
            for n, y, c in zip(relay_names, relay_birth_years, relay_cities, strict=False)
        ]
        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "form": form,
                "is_free": is_free,
                "relay_enabled": relay_enabled,
                "relay_max_members": competition.relay_max_members,
                "relay_members_post": relay_members_post,
            },
        )


class ParticipantListView(TemplateView):
    template_name = "registrations/participant_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = get_object_or_404(Competition, pk=self.kwargs["pk"], is_deleted=False)
        user = self.request.user
        is_manager = can_manage(user, competition)

        if is_manager:
            registrations = competition.registrations.select_related("category", "team", "user")
        else:
            qs = competition.registrations.filter(is_rejected=False)
            comp = competition
            if comp.require_approval and comp.require_payment:
                if comp.show_unapproved_in_list and comp.show_unpaid_in_list:
                    pass
                elif comp.show_unapproved_in_list and not comp.show_unpaid_in_list:
                    qs = qs.filter(is_paid=True)
                elif not comp.show_unapproved_in_list and comp.show_unpaid_in_list:
                    qs = qs.filter(is_approved=True)
                else:
                    qs = qs.filter(is_approved=True, is_paid=True)
            elif comp.require_approval:
                if not comp.show_unapproved_in_list:
                    qs = qs.filter(is_approved=True)
            elif comp.require_payment:
                if not comp.show_unpaid_in_list:
                    qs = qs.filter(is_paid=True)
            registrations = qs.select_related("category", "team")

        cats = list(competition.registration_categories.filter(is_deleted=False))
        context["competition"] = competition
        context["registrations"] = registrations
        context["is_manager"] = is_manager
        context["categories"] = cats
        context["category_stats"] = [
            {
                "category": cat,
                "count": competition.qualified_count(category=cat),
                "limit_reached": competition.is_limit_reached(category=cat),
            }
            for cat in cats
        ]
        context["qualified_count"] = competition.qualified_count()
        context["max_participants"] = competition.max_participants
        return context


class ApproveRegistrationView(View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        reg.is_approved = True
        reg.is_rejected = False
        reg.save(update_fields=["is_approved", "is_rejected"])
        return redirect("registrations:participant_list", pk=pk)


class RejectRegistrationView(View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        reg.is_rejected = True
        reg.is_approved = False
        reg.rejection_note = request.POST.get("rejection_note", "")
        reg.save(update_fields=["is_rejected", "is_approved", "rejection_note"])
        return redirect("registrations:participant_list", pk=pk)


class MarkPaidView(View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        reg.is_paid = True
        reg.save(update_fields=["is_paid"])
        return redirect("registrations:participant_list", pk=pk)


class EditRegistrationView(View):
    template_name = "registrations/edit_registration.html"

    def _get_objects(self, pk, reg_pk, user):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        return competition, reg

    def get(self, request, pk, reg_pk):
        competition, reg = self._get_objects(pk, reg_pk, request.user)
        service_only = competition.registration_mode == "self_only"
        form = EditRegistrationForm(instance=reg, competition=competition, service_fields_only=service_only)
        if not service_only:
            form.initial["team_name"] = reg.team.name if reg.team else ""
        return render(request, self.template_name, {"competition": competition, "registration": reg, "form": form})

    def post(self, request, pk, reg_pk):
        competition, reg = self._get_objects(pk, reg_pk, request.user)
        service_only = competition.registration_mode == "self_only"
        form = EditRegistrationForm(
            request.POST, instance=reg, competition=competition, service_fields_only=service_only
        )
        if form.is_valid():
            obj = form.save(commit=False)
            if not service_only:
                team_name = form.cleaned_data.get("team_name", "").strip()
                obj.team = Team.get_or_restore(team_name) if team_name else None
            obj.save()
            return redirect("registrations:participant_list", pk=pk)
        return render(request, self.template_name, {"competition": competition, "registration": reg, "form": form})


class DeleteRegistrationView(View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        reg.delete()
        return redirect("registrations:participant_list", pk=pk)


class ManualAddRegistrationView(View):
    template_name = "registrations/manual_add.html"

    def _get_competition(self, pk, user):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(user, competition):
            raise PermissionDenied
        if competition.registration_mode != "free":
            raise PermissionDenied
        return competition

    def get(self, request, pk):
        competition = self._get_competition(pk, request.user)
        form = RegistrationForm(competition=competition)
        form.fields["category"].queryset = RegistrationCategory.objects.filter(
            competition=competition, is_deleted=False
        )
        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "form": form,
                "relay_enabled": competition.relay_enabled,
                "relay_max_members": competition.relay_max_members,
            },
        )

    def post(self, request, pk):
        competition = self._get_competition(pk, request.user)
        relay_enabled = competition.relay_enabled
        relay_names = []
        relay_birth_years = []
        relay_cities = []
        if relay_enabled:
            relay_names = [n.strip() for n in request.POST.getlist("participant_name") if n.strip()]
            relay_birth_years = [y.strip() for y in request.POST.getlist("participant_birth_year")]
            relay_cities = [c.strip() for c in request.POST.getlist("participant_city")]
            relay_birth_years = (relay_birth_years + [""] * len(relay_names))[: len(relay_names)]
            relay_cities = (relay_cities + [""] * len(relay_names))[: len(relay_names)]

        form = RegistrationForm(request.POST, competition=competition)
        form.fields["category"].queryset = RegistrationCategory.objects.filter(
            competition=competition, is_deleted=False
        )

        relay_members_post = [
            {"name": n, "birth_year": y, "city": c}
            for n, y, c in zip(relay_names, relay_birth_years, relay_cities, strict=False)
        ]
        ctx = {
            "competition": competition,
            "form": form,
            "relay_enabled": relay_enabled,
            "relay_max_members": competition.relay_max_members,
            "relay_members_post": relay_members_post,
        }

        if relay_enabled:
            if not relay_names:
                form.add_error(None, "At least one participant name is required.")
            elif len(relay_names) > competition.relay_max_members:
                form.add_error(None, f"Maximum {competition.relay_max_members} members allowed.")

        if form.is_valid() and not form.errors:
            cleaned = form.cleaned_data
            first_name = "" if relay_enabled else cleaned["first_name"]
            last_name = "" if relay_enabled else cleaned["last_name"]
            gender = cleaned["gender"]
            category = cleaned.get("category")

            if relay_enabled and relay_birth_years:
                try:
                    birth_date = datetime.date(int(relay_birth_years[0]), 1, 1)
                except (ValueError, TypeError):
                    birth_date = datetime.date(1900, 1, 1)
            else:
                birth_date = cleaned.get("birth_date") or (
                    datetime.date(cleaned["birth_year"], 1, 1)
                    if cleaned.get("birth_year")
                    else datetime.date(1900, 1, 1)
                )

            cat_ok = not category or (
                category.is_open()
                and (category.matches_gender(gender) if relay_enabled else category.matches(gender, birth_date))
            )
            if not cat_ok:
                form.add_error("category", "This category is not available.")
                return render(request, self.template_name, ctx)

            if not relay_enabled and check_duplicate(competition, None, first_name, last_name, birth_date):
                form.add_error(None, "A participant with this name and birth year is already registered.")
                return render(request, self.template_name, ctx)

            team_name = cleaned.get("team_name", "").strip()
            team = Team.get_or_restore(team_name) if team_name else None
            CompetitionRegistration.objects.create(
                competition=competition,
                registered_by=request.user,
                first_name=first_name,
                last_name=last_name,
                participant_names="<BR>".join(relay_names) if relay_enabled else "",
                participant_birth_years="<BR>".join(relay_birth_years) if relay_enabled else "",
                participant_cities="<BR>".join(relay_cities) if relay_enabled else "",
                birth_date=birth_date,
                gender=gender,
                category=category,
                city="" if relay_enabled else cleaned.get("city", ""),
                team=team,
                additional_info=cleaned.get("additional_info", ""),
            )
            return redirect("registrations:participant_list", pk=pk)

        return render(request, self.template_name, ctx)


class ParticipantsAPIView(View):
    def get(self, request):
        token = request.GET.get("token", "").strip()
        if not token:
            return JsonResponse({"error": "token required"}, status=400)
        try:
            competition = Competition.objects.get(upload_token=token)
        except (Competition.DoesNotExist, Exception):
            return JsonResponse({"error": "invalid token"}, status=401)
        if competition.status != Competition.Status.APPROVED or competition.is_deleted:
            return JsonResponse({"error": "competition not found"}, status=401)

        qs = competition.registrations.filter(is_rejected=False).select_related("category", "team")
        if competition.require_approval:
            qs = qs.filter(is_approved=True)
        if competition.require_payment:
            qs = qs.filter(is_paid=True)

        participant_list = list(qs)
        referenced_category_ids = {r.category_id for r in participant_list if r.category_id}
        categories = RegistrationCategory.objects.filter(pk__in=referenced_category_ids)

        data = {
            "competition_id": competition.pk,
            "competition_title": competition.title,
            "birth_date_mode": competition.birth_date_mode,
            "registration_mode": competition.registration_mode,
            "require_approval": competition.require_approval,
            "require_payment": competition.require_payment,
            "categories": [
                {
                    "id": c.pk,
                    "name": c.name,
                    "male": c.male,
                    "female": c.female,
                    "birth_from": c.birth_from.isoformat() if c.birth_from else None,
                    "birth_to": c.birth_to.isoformat() if c.birth_to else None,
                    "laps": c.laps,
                    "bib_from": c.bib_from if c.bib_from is not None else 1,
                    "bib_to": c.bib_to if c.bib_to is not None else 20000,
                }
                for c in categories
            ],
            "participants": [
                {
                    "id": r.pk,
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "participant_names": r.participant_names
                    if r.participant_names
                    else f"{r.last_name} {r.first_name}".strip(),
                    "participant_birth_years": r.participant_birth_years
                    if r.participant_birth_years
                    else str(r.birth_date.year),
                    "participant_cities": r.participant_cities if r.participant_cities else r.city,
                    "birth_date": r.birth_date.isoformat(),
                    "birth_year": r.birth_date.year,
                    "gender": r.gender,
                    "category_id": r.category_id,
                    "category_name": r.category.name if r.category else "",
                    "team": r.team.name if r.team else "",
                    "city": r.city,
                    "additional_info": r.additional_info,
                    "is_approved": r.is_approved,
                    "is_paid": r.is_paid,
                }
                for r in participant_list
            ],
        }
        return JsonResponse(data)


class ExportParticipantsCSVView(View):
    def get(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="participants_{pk}.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "#",
                "Participant(s)",
                "Last name",
                "First name",
                "Gender",
                "Birth date",
                "Birth year(s)",
                "City/Cities",
                "Category",
                "Team",
                "Additional info",
                "Approved",
                "Paid",
                "Rejected",
                "Registered at",
            ]
        )
        for i, reg in enumerate(competition.registrations.select_related("category", "team"), start=1):
            writer.writerow(
                [
                    i,
                    reg.participant_names.replace("<BR>", "; ")
                    if reg.participant_names
                    else f"{reg.last_name} {reg.first_name}".strip(),
                    reg.last_name,
                    reg.first_name,
                    reg.gender,
                    reg.birth_date.isoformat(),
                    reg.participant_birth_years.replace("<BR>", "; ")
                    if reg.participant_birth_years
                    else str(reg.birth_date.year),
                    reg.participant_cities.replace("<BR>", "; ") if reg.participant_cities else reg.city,
                    reg.category.name if reg.category else "",
                    reg.team.name if reg.team else "",
                    reg.additional_info,
                    reg.is_approved,
                    reg.is_paid,
                    reg.is_rejected,
                    reg.registered_at.strftime("%Y-%m-%d %H:%M"),
                ]
            )
        return response


class TeamAutocompleteView(View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        qs = Team.objects.filter(is_deleted=False)
        if q:
            qs = qs.filter(name__icontains=q)
        data = [{"id": t.pk, "name": t.name} for t in qs[:20]]
        return JsonResponse({"results": data})


class CityAutocompleteView(View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        qs = CompetitionRegistration.objects.exclude(city="").values_list("city", flat=True).distinct()
        if q:
            qs = qs.filter(city__icontains=q)
        cities = sorted(set(qs[:50]))
        return JsonResponse({"results": [{"name": c} for c in cities]})
