import csv
import datetime
import json
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.translation import gettext
from django.views import View
from django.views.generic import TemplateView

from accounts import managing
from accounts.access import ParticipantRequiredMixin
from calendar_app.models import Competition
from calendar_app.visibility import can_see, manages, public_events_q

from . import registering
from .forms import EditRegistrationForm, RegistrationForm
from .models import CompetitionRegistration, RegistrationCategory, Team, check_duplicate, counted_q, counts


def can_manage(user, competition) -> bool:
    return manages(user, competition)


def can_self_edit(user, competition, reg, member_ids=None) -> bool:
    """Whether ``user`` may edit/cancel ``reg`` as its owner, or for its owner (not as a manager).

    Managers are handled separately and take precedence; this covers a plain participant
    acting on their own entry while registration is open (by deadline -- the participant limit
    is ignored since they already hold a slot) and the entry is not rejected -- and, on the same
    terms, whoever manages the participant's registrations (issue #315). Authorization is keyed on
    the stored ``reg.user`` only, never on request data. ``member_ids``, when given, are the members
    ``user`` manages, asked once for a page of many rows.
    """
    if not (
        user.is_authenticated
        and reg.user_id is not None
        and not reg.is_rejected
        and competition.is_registration_open(ignore_limit=True)
    ):
        return False
    if reg.user_id == user.id:
        return True
    return reg.user_id in member_ids if member_ids is not None else managing.acts_for(user, reg.user_id)


class RegisterForCompetitionView(ParticipantRequiredMixin, View):
    template_name = "registrations/register.html"

    def _get_competition(self, pk):
        return get_object_or_404(Competition, pk=pk, is_deleted=False)

    def _many(self, request, competition, rows, nobody=False):
        """The page for several (issue #315): the reader and the members they manage, ticked."""
        return render(
            request,
            "registrations/register_many.html",
            {
                "competition": competition,
                "rows": rows,
                "nobody": nobody,
                "is_free": registering.is_free(competition),
                "relay_enabled": False,
                "all_categories_json": self._categories_json(competition),
            },
        )

    def _post_many(self, request, competition, rows):
        """Enter whoever was ticked on the page for several, from the top; the page again if anyone
        could not be."""
        if not registering.ticks_allowed(competition, request.user, request.POST):
            raise PermissionDenied
        if not request.POST.getlist("person"):
            return self._many(request, competition, rows, nobody=True)
        if registering.enter_rows(competition, rows, request.user, request.POST):
            return redirect("registrations:participant_list", pk=competition.pk)
        return self._many(request, competition, rows)

    @staticmethod
    def _categories_json(competition):
        categories = RegistrationCategory.objects.filter(competition=competition, is_deleted=False)
        return json.dumps(
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
                for c in categories
            ]
        )

    def _page(self, request, competition, form, relay_members_post=()):
        """The page as first shown and as shown again after a refusal: one context for both, so a
        refused entry keeps the category filter working and the relay team as it was typed."""
        user = request.user
        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "form": form,
                "profile_incomplete": not user.gender or not user.birth_date,
                "is_free": competition.registration_mode == competition.RegistrationMode.FREE,
                "relay_enabled": competition.relay_enabled,
                "relay_max_members": competition.relay_max_members,
                "relay_members_post": relay_members_post,
                "all_categories_json": self._categories_json(competition),
            },
        )

    def get(self, request, pk):
        competition = self._get_competition(pk)
        if not can_see(request.user, competition):
            raise Http404
        if competition.status != Competition.Status.APPROVED and not can_manage(request.user, competition):
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

        rows = registering.rows_for(competition, request.user)
        if rows is not None:
            return self._many(request, competition, rows)
        return self._page(request, competition, registering.blank_form(competition, request.user))

    def post(self, request, pk):
        competition = self._get_competition(pk)
        if not can_see(request.user, competition):
            raise Http404
        if competition.status != Competition.Status.APPROVED and not can_manage(request.user, competition):
            raise Http404
        if not competition.is_registration_open():
            raise PermissionDenied

        user = request.user
        rows = registering.rows_for(competition, user)
        if rows is not None:
            return self._post_many(request, competition, rows)
        if not registering.is_free(competition) and registering.profile_incomplete(user):
            raise PermissionDenied

        form = registering.bound_form(competition, user, request.POST)

        relay_enabled = competition.relay_enabled
        relay_names_raw: list[str] = []
        relay_birth_years_raw: list[str] = []
        relay_cities_raw: list[str] = []
        relay_names: list[str] = []
        relay_birth_years: list[str] = []
        relay_cities: list[str] = []
        if relay_enabled:
            relay_names_raw = [n.strip() for n in request.POST.getlist("participant_name") if n.strip()]
            relay_birth_years_raw = [y.strip() for y in request.POST.getlist("participant_birth_year")]
            relay_cities_raw = [c.strip() for c in request.POST.getlist("participant_city")]
            # Pad / trim auxiliary lists to match names length
            relay_birth_years_raw = (relay_birth_years_raw + [""] * len(relay_names_raw))[: len(relay_names_raw)]
            relay_cities_raw = (relay_cities_raw + [""] * len(relay_names_raw))[: len(relay_names_raw)]
            # HTML-escape for DB storage (participant_names rendered with |safe in templates)
            relay_names = [escape(n) for n in relay_names_raw]
            relay_birth_years = [escape(y) for y in relay_birth_years_raw]
            relay_cities = [escape(c) for c in relay_cities_raw]
            if not relay_names:
                form.add_error(None, gettext("At least one participant name is required."))
            elif len(relay_names) > competition.relay_max_members:
                form.add_error(
                    None, gettext("Maximum %(count)s members allowed.") % {"count": competition.relay_max_members}
                )

        relay_members_post = [
            {"name": n, "birth_year": y, "city": c}
            for n, y, c in zip(relay_names_raw, relay_birth_years_raw, relay_cities_raw, strict=False)
        ]
        relay = (relay_names, relay_birth_years, relay_cities) if relay_enabled else None
        if (
            form.is_valid()
            and not form.errors
            and registering.register_one(competition, form, user, registered_by=user, relay=relay)
        ):
            return redirect("registrations:participant_list", pk=competition.pk)
        return self._page(request, competition, form, relay_members_post)


def _number_rows(rows, start, counts, taken):
    """Pair each row with its number: from ``start`` upward, skipping numbers already handed out.

    ``taken`` is the set of numbers this event has already given to earlier sections, and it is
    updated as numbers are used. Skipping is what keeps two categories sharing a range -- both
    written as 61-120, which is how an organizer says "the men are the 61 to 120 block" -- from
    handing the same number to two riders: the first category fills the block from its start and
    the next continues after it.
    """
    numbered = []
    candidate = start
    for reg in rows:
        if not counts(reg):
            numbered.append((None, reg))
            continue
        while candidate in taken:
            candidate += 1
        numbered.append((candidate, reg))
        taken.add(candidate)
        candidate += 1
    return numbered


def build_participant_groups(registrations, categories, counts=None):
    """Group registrations into per-category sections with bib-range numbering.

    ``categories`` is the ordered list of category objects to render as sections. A row's number
    starts at the category's ``bib_from`` (default 1) and counts up, but **never repeats a number
    already given out in this event**: a number another section took is skipped. Two categories
    written with the same range therefore share it in order -- the first fills it from the start,
    the next carries on where that one stopped -- while a category whose range sits somewhere else
    entirely still begins exactly at its own ``bib_from``.

    ``counts`` (default: everyone) decides which rows get a number; non-counting rows get ``None``
    and do not consume one. Registrations with no category form a trailing section numbered from 1
    (skipping what is taken, like any other), and categories with no registrations are omitted --
    an empty category reserves nothing, because a number belongs to a rider, not to a section.
    """
    if counts is None:
        counts = lambda reg: True  # noqa: E731
    buckets: dict[int | None, list] = defaultdict(list)
    for reg in registrations:
        buckets[reg.category_id].append(reg)
    taken: set[int] = set()

    def _section(category, rows, start):
        numbered = _number_rows(rows, start, counts, taken)
        shown = sum(1 for number, _ in numbered if number is not None)
        return {"category": category, "count": shown, "rows": numbered}

    groups = []
    for category in categories:
        rows = buckets.get(category.pk)
        if rows:
            start = category.bib_from if category.bib_from is not None else 1
            groups.append(_section(category, rows, start))
    uncategorized = buckets.get(None)
    if uncategorized:
        groups.append(_section(None, uncategorized, 1))
    return groups


class ParticipantListView(TemplateView):
    template_name = "registrations/participant_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = get_object_or_404(Competition, pk=self.kwargs["pk"], is_deleted=False)
        user = self.request.user
        is_manager = can_manage(user, competition)

        if not can_see(user, competition):
            raise Http404
        if competition.status != Competition.Status.APPROVED and not is_manager:
            raise Http404

        # The reader's own entries and those of the members they manage (issue #315)
        owned = {user.id} | managing.member_ids(user) if user.is_authenticated else set()
        if is_manager:
            registrations = list(competition.registrations.select_related("category", "team", "user", "registered_by"))
        else:
            registrations = list(self._public_registrations(competition, owned))

        cats = list(competition.registration_categories.filter(is_deleted=False))
        # Sections cover active categories plus any (soft-deleted) category a shown
        # registration still points to, so nobody's category silently disappears.
        referenced_ids = {reg.category_id for reg in registrations if reg.category_id}
        section_categories = list(
            competition.registration_categories.filter(Q(is_deleted=False) | Q(pk__in=referenced_ids)).order_by(
                "order", "pk"
            )
        )
        context["competition"] = competition
        context["registrations"] = registrations
        context["participant_groups"] = build_participant_groups(
            registrations, section_categories, counts=lambda reg: counts(reg, competition)
        )
        context["is_manager"] = is_manager
        # A signed-in participant (not a manager) gets Edit/Cancel controls on their own rows and on
        # those of the members they manage while registration is open. Compute once so the template
        # can add an actions column.
        context["owned_ids"] = owned
        context["show_owner_actions"] = (
            not is_manager
            and user.is_authenticated
            and competition.is_registration_open(ignore_limit=True)
            and any(reg.user_id in owned for reg in registrations)
        )
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

    def _public_registrations(self, competition, owned):
        qs = competition.registrations.filter(is_rejected=False)
        visibility = Q()
        if competition.require_approval and not competition.show_unapproved_in_list:
            visibility &= Q(is_approved=True)
        if competition.require_payment and not competition.show_unpaid_in_list:
            visibility &= Q(is_paid=True)
        if visibility:
            # Hidden-until-qualified rules apply, but a signed-in owner must still see (and be
            # able to edit) their own not-yet-qualified entry -- and their members' -- so always
            # include those rows.
            qs = qs.filter(visibility | Q(user_id__in=owned)) if owned else qs.filter(visibility)
        return qs.select_related("category", "team")


class ApproveRegistrationView(LoginRequiredMixin, View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        reg.is_approved = True
        reg.is_rejected = False
        reg.save(update_fields=["is_approved", "is_rejected"])
        return redirect("registrations:participant_list", pk=pk)


class RejectRegistrationView(LoginRequiredMixin, View):
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


class MarkPaidView(LoginRequiredMixin, View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        reg.is_paid = True
        reg.save(update_fields=["is_paid"])
        return redirect("registrations:participant_list", pk=pk)


class EditRegistrationView(LoginRequiredMixin, View):
    template_name = "registrations/edit_registration.html"

    def _get_objects(self, pk, reg_pk, user):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        # Manager rights take precedence: a manager (incl. the event owner) editing their own
        # registration still gets the admin controls, not the restricted participant form.
        if can_manage(user, competition):
            mode = "manager"
        elif can_self_edit(user, competition, reg):
            mode = "owner"
        else:
            raise PermissionDenied
        return competition, reg, mode

    def _build_form(self, competition, reg, mode, data=None):
        if mode == "owner":
            return EditRegistrationForm(data, instance=reg, competition=competition, participant_fields_only=True)
        service_only = competition.registration_mode == competition.RegistrationMode.SELF_ONLY
        return EditRegistrationForm(data, instance=reg, competition=competition, service_fields_only=service_only)

    def get(self, request, pk, reg_pk):
        competition, reg, mode = self._get_objects(pk, reg_pk, request.user)
        form = self._build_form(competition, reg, mode)
        if "team_name" in form.fields:
            form.initial["team_name"] = reg.team.name if reg.team else ""
        return render(request, self.template_name, {"competition": competition, "registration": reg, "form": form})

    def post(self, request, pk, reg_pk):
        competition, reg, mode = self._get_objects(pk, reg_pk, request.user)
        was_approved = reg.is_approved
        form = self._build_form(competition, reg, mode, data=request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if "team_name" in form.fields:
                team_name = form.cleaned_data.get("team_name", "").strip()
                obj.team = Team.get_or_restore(team_name) if team_name else None
            # A participant editing an already-approved entry sends it back to moderation, so
            # the organiser re-checks the changed data instead of it going through silently.
            if mode == "owner" and competition.require_approval and was_approved and form.has_changed():
                obj.is_approved = False
            obj.save()
            return redirect("registrations:participant_list", pk=pk)
        return render(request, self.template_name, {"competition": competition, "registration": reg, "form": form})


class DeleteRegistrationView(LoginRequiredMixin, View):
    def post(self, request, pk, reg_pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        reg = get_object_or_404(CompetitionRegistration, pk=reg_pk, competition=competition)
        # Managers may delete any entry; a participant may cancel only their own, and only
        # while registration is still open (:func:`can_self_edit`).
        if not (can_manage(request.user, competition) or can_self_edit(request.user, competition, reg)):
            raise PermissionDenied
        reg.delete()
        return redirect("registrations:participant_list", pk=pk)


class ManualAddRegistrationView(LoginRequiredMixin, View):
    template_name = "registrations/manual_add.html"

    def _get_competition(self, pk, user):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(user, competition):
            raise PermissionDenied
        if competition.registration_mode != competition.RegistrationMode.FREE:
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
        relay_names_raw: list[str] = []
        relay_birth_years_raw: list[str] = []
        relay_cities_raw: list[str] = []
        relay_names: list[str] = []
        relay_birth_years: list[str] = []
        relay_cities: list[str] = []
        if relay_enabled:
            relay_names_raw = [n.strip() for n in request.POST.getlist("participant_name") if n.strip()]
            relay_birth_years_raw = [y.strip() for y in request.POST.getlist("participant_birth_year")]
            relay_cities_raw = [c.strip() for c in request.POST.getlist("participant_city")]
            relay_birth_years_raw = (relay_birth_years_raw + [""] * len(relay_names_raw))[: len(relay_names_raw)]
            relay_cities_raw = (relay_cities_raw + [""] * len(relay_names_raw))[: len(relay_names_raw)]
            relay_names = [escape(n) for n in relay_names_raw]
            relay_birth_years = [escape(y) for y in relay_birth_years_raw]
            relay_cities = [escape(c) for c in relay_cities_raw]

        form = RegistrationForm(request.POST, competition=competition)
        form.fields["category"].queryset = RegistrationCategory.objects.filter(
            competition=competition, is_deleted=False
        )

        relay_members_post = [
            {"name": n, "birth_year": y, "city": c}
            for n, y, c in zip(relay_names_raw, relay_birth_years_raw, relay_cities_raw, strict=False)
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
                form.add_error(None, gettext("At least one participant name is required."))
            elif len(relay_names) > competition.relay_max_members:
                form.add_error(
                    None, gettext("Maximum %(count)s members allowed.") % {"count": competition.relay_max_members}
                )

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

            with transaction.atomic():
                competition = Competition.objects.select_for_update().get(pk=competition.pk)
                cat_ok = not category or (
                    category.is_open()
                    and (category.matches_gender(gender) if relay_enabled else category.matches(gender, birth_date))
                )
                if not cat_ok:
                    form.add_error("category", gettext("This category is not available."))
                    return render(request, self.template_name, ctx)

                if not relay_enabled and check_duplicate(competition, None, first_name, last_name, birth_date):
                    form.add_error(None, gettext("A participant with this name and birth year is already registered."))
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
                    is_approved=not competition.require_approval,
                    is_paid=not competition.require_payment,
                )
            return redirect("registrations:participant_list", pk=pk)

        return render(request, self.template_name, ctx)


def _csv_row(row: list) -> list:
    """Cells a spreadsheet shows as text: a participant's own entry starting with =, +, - or @ (or a
    tab or a return) is otherwise run as a formula when the organizer opens the file in Excel."""
    return ["'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v for v in row]


class ExportParticipantsCSVView(LoginRequiredMixin, View):
    def get(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="participants_{pk}.csv"'
        writer = csv.writer(response)
        writer.writerow(
            _csv_row(
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
                    # The organizer's own wording when there is one, and the English default otherwise:
                    # every other header in this file is English, and a script that reads the export
                    # should not see the column rename itself with the exporter's interface language.
                    competition.additional_info_label.strip() or "Additional info",
                    "Approved",
                    "Paid",
                    "Rejected",
                    "Registered at",
                ]
            )
        )
        for i, reg in enumerate(competition.registrations.select_related("category", "team"), start=1):
            writer.writerow(
                _csv_row(
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
        qs = (
            CompetitionRegistration.objects.filter(public_events_q("competition__"), counted_q())
            .exclude(city="")
            .values_list("city", flat=True)
            .distinct()
        )
        if q:
            qs = qs.filter(city__icontains=q)
        cities = sorted(set(qs[:50]))
        return JsonResponse({"results": [{"name": c} for c in cities]})
