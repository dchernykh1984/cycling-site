import datetime
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from accounts.access import ParticipantRequiredMixin
from accounts.models import User
from locations.models import (
    Location,
    LocationConflictError,
    LocationProposal,
    chain_is_approved,
    lock_competition_location,
    map_display_node,
    sort_locations_for_filter,
)

from .forms import (
    AddCompetitionCommentForm,
    CompetitionFilterForm,
    RegistrationSettingsForm,
    RejectCompetitionForm,
    SubmitCompetitionForm,
)
from .models import (
    Competition,
    CompetitionComment,
    CompetitionFavorite,
    Discipline,
    DisciplineCategory,
    EventType,
)

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)


def _get_locations_data(user=None) -> list:
    """Approved Location nodes (+ the given user's own pending proposals) in 3 languages.

    Includes hidden depth-4 fallback venue nodes so that JS can use them for
    auto-assignment when no real venue is selected. Pending locations are visible
    only to the user who proposed them, so they can pick their own before approval.
    """
    # Public = no proposal or an approved one; a pending proposal is visible only to its proposer.
    visible = Q(proposal__isnull=True) | Q(proposal__status=LocationProposal.Status.APPROVED)
    if user is not None and getattr(user, "is_authenticated", False):
        visible |= Q(proposal__status=LocationProposal.Status.PENDING_APPROVAL, proposal__submitted_by=user)
    rows = list(
        Location.objects.filter(is_deleted=False)
        .filter(visible)
        .order_by("sort_order", "path")
        .values("pk", "depth", "path", "name_ru", "name_kk", "name_en", "is_hidden", "lat", "lng")
    )
    # Coordinates let the form render existing venues as map markers (issue #118).
    for row in rows:
        row["lat"] = float(row["lat"]) if row["lat"] is not None else None
        row["lng"] = float(row["lng"]) if row["lng"] is not None else None
    # Hidden / coordinate-less nodes sink to the end of each cascade dropdown level: the
    # filters build options by filtering this list in order (see sort_locations_for_filter).
    return sort_locations_for_filter(rows)


def _can_manage_any_competition(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


def _is_organizer_plus(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ORGANIZER_RANK)


def _unpublish_if_geography_is_pending(comp, user) -> None:
    """Send a published event back for review when it is re-pointed at unreviewed geography.

    Publishing a branch by editing an event into it is the same leak as approving the event there,
    and it leaves the branch holding approved work, which is what blocks its rejection.
    """
    # Only the geography *above* the venue matters, as in Competition.approve and the API PATCH: a
    # freshly proposed start-point venue under an approved city is the intended flow and stays
    # published. Checking the venue too would needlessly un-publish that.
    parent = comp.location.get_parent() if comp.location is not None else None
    if (
        comp.status == Competition.Status.APPROVED
        and not _can_manage_any_competition(user)
        and comp.location is not None
        and not chain_is_approved(parent)
    ):
        comp.status = Competition.Status.PENDING_APPROVAL
        comp.approved_by = None
        comp.approved_at = None


def _resolve_competition_location(cd, user, *, approved):
    """Location for a competition: a freshly proposed venue if the form asked for one.

    Organizer+ submitters get an approved venue directly; everyone else proposes a
    pending venue they can use immediately (issue #111).
    """
    new_name = (cd.get("new_venue_name") or "").strip()
    city = cd.get("new_venue_city")
    if new_name and city is not None:
        return Location.propose_venue(
            city,
            new_name,
            cd.get("new_venue_lat"),
            cd.get("new_venue_lng"),
            submitted_by=user,
            # A venue is only public where the geography above it is. The submitter may pick their
            # own pending city here, and publishing a venue inside it would leak that city through
            # the competition and leave the branch holding approved work, which blocks its rejection.
            approved=approved and chain_is_approved(city),
        )
    return cd.get("location")


def _disciplines_for_locale() -> list:
    """Disciplines with the name resolved for the active language.

    Uses the model's translated ``name`` (modeltranslation fallback ru->en->kk) rather than the raw
    ``name_<lang>`` column: an empty translation would otherwise yield blank picker options that
    collapse distinct disciplines into one checkbox via the cascade's name de-duplication.
    """
    return [{"pk": d.pk, "name": d.name, "category_id": d.category_id} for d in Discipline.objects.all()]


def _selected_discipline_ids(form) -> list:
    """The discipline ids currently chosen on the submit/edit form (initial ints or POSTed
    strings), as a JSON-serializable list so the discipline picker can restore its state."""
    selected: list[int] = []
    for value in form["disciplines"].value() or []:
        try:
            pk = int(value)
        except (TypeError, ValueError):
            continue
        if pk not in selected:
            selected.append(pk)
    return selected


def _categories_for_locale() -> list:
    """Direction categories with the name resolved for the active language (modeltranslation fallback)."""
    return [{"pk": c.pk, "name": c.name} for c in DisciplineCategory.objects.all()]


def _discipline_picker_context(form) -> dict:
    """Context for the direction->discipline cascade discipline picker on the submit/edit forms.

    ``discipline_categories_json`` is keyed distinctly from the registration ``categories_json``
    those views already pass, so the two never collide.
    """
    return {
        "discipline_categories_json": _categories_for_locale(),
        "disciplines_json": _disciplines_for_locale(),
        "selected_disciplines": _selected_discipline_ids(form),
    }


def _event_types_for_locale() -> list:
    """Event types with the name resolved for the active language (modeltranslation fallback)."""
    return [{"pk": e.pk, "name": e.name} for e in EventType.objects.all()]


def _parse_date(value, default):
    """Parse an ISO date string, falling back to ``default`` on missing/invalid input."""
    if value:
        try:
            return datetime.date.fromisoformat(value)
        except (ValueError, TypeError):
            return default
    return default


def _parse_int_ids(values) -> set:
    """Flatten GET values into a set of ints; ignore non-integer junk.

    Each value may itself be a comma-joined group of ids (same-name nodes merged
    into one multi-select choice), and several values may be passed via getlist.
    """
    ids: set[int] = set()
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except (ValueError, TypeError):
                continue
    return ids


def _location_descendant_pks(location_ids) -> set:
    """Union of descendant pks (incl. self) for all given location ids."""
    ids = _parse_int_ids(location_ids)
    if not ids:
        return set()
    pks: set[int] = set()
    for loc in Location.objects.filter(pk__in=ids):
        pks.update(loc.get_descendants(include_self=True).values_list("pk", flat=True))
    return pks


def _apply_id_filters(qs, event_type_ids, discipline_ids, direction_ids):
    """Apply integer-keyed multi-select filters; non-integer values are ignored.

    Each argument is a list of GET values (each value may itself be a comma-joined
    group of ids). A competition matches if it has at least one of the selected
    disciplines OR at least one discipline in a selected direction (category); the two are
    OR-ed so a direction picked without drilling into a discipline still filters alongside
    another direction's discipline. ``disciplines`` is a many-to-many, so de-duplicate the join.
    """
    event_types = _parse_int_ids(event_type_ids)
    if event_types:
        qs = qs.filter(event_type_id__in=event_types)
    disciplines = _parse_int_ids(discipline_ids)
    directions = _parse_int_ids(direction_ids)
    if disciplines or directions:
        match = Q()
        if disciplines:
            match |= Q(disciplines__in=disciplines)
        if directions:
            match |= Q(disciplines__category_id__in=directions)
        qs = qs.filter(match).distinct()
    return qs


def _only_favorite_requested(request) -> bool:
    """Whether the ``?favorite`` flag asks to show only the current user's favorites (issue #183)."""
    return (request.GET.get("favorite") or "").strip().lower() in ("1", "true", "on", "yes")


def _apply_favorite_filter(qs, request):
    """Restrict ``qs`` to the user's favorites when ``?favorite`` is set; anonymous users have none."""
    if not _only_favorite_requested(request):
        return qs
    if not request.user.is_authenticated:
        return qs.none()
    return qs.filter(favorited_by__user=request.user)


def _favorited_ids(request, competitions) -> set:
    """Ids among ``competitions`` the current user has favorited (empty for anonymous).

    ``competitions`` may be a queryset or an already-fetched sequence of competitions -- the list
    view passes the evaluated page rows so the page query is not re-run as an ``IN`` subquery.
    """
    if not request.user.is_authenticated:
        return set()
    return set(
        CompetitionFavorite.objects.filter(user=request.user, competition__in=competitions).values_list(
            "competition_id", flat=True
        )
    )


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
        context["discipline_categories"] = DisciplineCategory.objects.all()
        context["event_types_json"] = _event_types_for_locale()
        context["categories_json"] = _categories_for_locale()
        context["disciplines_json"] = _disciplines_for_locale()
        context["locations_data"] = _get_locations_data()
        context["only_favorite"] = _only_favorite_requested(self.request)
        return context


class CalendarEventsAPIView(View):
    def get(self, request):
        from django.db.models import Q

        is_manager = _can_manage_any_competition(request.user)
        qs = (
            Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False)
            .select_related("event_type")
            .prefetch_related("disciplines__category")
        )
        if not is_manager:
            qs = qs.filter(is_hidden=False)
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
        qs = _apply_id_filters(
            qs,
            request.GET.getlist("event_type"),
            request.GET.getlist("discipline"),
            request.GET.getlist("direction"),
        )
        location_ids = request.GET.getlist("location")
        if location_ids:
            qs = qs.filter(location_id__in=_location_descendant_pks(location_ids))
        qs = _apply_favorite_filter(qs, request)

        # Evaluate once (with its select_related/prefetch) and reuse the rows for the favorite
        # lookup, so the events query is not re-run as an IN subquery just to flag favorites.
        competitions = list(qs)
        favorited_ids = _favorited_ids(request, competitions)
        events = [
            {
                "id": comp.pk,
                "title": comp.title,
                "start": comp.date_start.isoformat(),
                "end": comp.get_calendar_end(),
                "url": reverse("competition_detail", args=[comp.pk]),
                "extendedProps": {
                    "event_type": comp.event_type.name if comp.event_type else "",
                    "discipline": comp.disciplines_label,
                    "favorite": comp.pk in favorited_ids,
                },
            }
            for comp in competitions
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

        is_manager = _can_manage_any_competition(self.request.user)
        qs = (
            Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False)
            .select_related("event_type", "location")
            .prefetch_related("disciplines__category")
        )
        if not is_manager:
            qs = qs.filter(is_hidden=False)

        if form.is_valid():
            if form.cleaned_data.get("date_from"):
                date_from = form.cleaned_data["date_from"]
            if form.cleaned_data.get("date_to"):
                date_to = form.cleaned_data["date_to"]

        qs = _apply_id_filters(
            qs,
            self.request.GET.getlist("event_type"),
            self.request.GET.getlist("discipline"),
            self.request.GET.getlist("discipline_category"),
        )
        location_ids = self.request.GET.getlist("location")
        if location_ids:
            qs = qs.filter(location_id__in=_location_descendant_pks(location_ids))
        qs = _apply_favorite_filter(qs, self.request)

        qs = qs.filter(date_start__gte=date_from, date_start__lte=date_to).order_by("date_start")
        paginator = Paginator(qs, 20)
        page = paginator.get_page(self.request.GET.get("page", 1))
        context["competitions"] = page
        # Pass the evaluated page rows (not the sliced queryset) so the star lookup reuses them
        # instead of re-running the paginated query as an IN subquery.
        context["favorited_ids"] = _favorited_ids(self.request, list(page))
        context["only_favorite"] = _only_favorite_requested(self.request)
        context["filter_form"] = form
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["is_manager"] = is_manager
        context["discipline_categories"] = DisciplineCategory.objects.all()
        context["event_types_json"] = _event_types_for_locale()
        context["categories_json"] = _categories_for_locale()
        context["disciplines_json"] = _disciplines_for_locale()
        context["locations_data"] = _get_locations_data()
        return context


class CalendarMapView(TemplateView):
    template_name = "calendar_app/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context["date_from"] = _parse_date(self.request.GET.get("date_from"), today)
        context["date_to"] = _parse_date(self.request.GET.get("date_to"), today + datetime.timedelta(days=30))
        context["event_types_json"] = _event_types_for_locale()
        context["categories_json"] = _categories_for_locale()
        context["disciplines_json"] = _disciplines_for_locale()
        context["only_favorite"] = _only_favorite_requested(self.request)
        return context


class CalendarMapAPIView(View):
    """Locations that have competitions matching the filters.

    Filters: date range + event type + direction/discipline (no location filter -
    the map itself is the location view). A competition attached to a hidden "other
    location" venue (or any venue without coordinates) is shown at the nearest ancestor
    with coordinates (city -> region -> country), labelled with that ancestor's name, so
    the city appears rather than an "other location" pin (issue #113). Each marker
    carries its matching competitions so the popup can link to them.
    """

    def get(self, request):
        is_manager = _can_manage_any_competition(request.user)
        qs = Competition.objects.filter(
            status=Competition.Status.APPROVED,
            is_deleted=False,
            location__isnull=False,
            location__is_deleted=False,
        ).select_related("location")
        if not is_manager:
            qs = qs.filter(is_hidden=False)
        date_from = _parse_date(request.GET.get("date_from"), None)
        date_to = _parse_date(request.GET.get("date_to"), None)
        if date_from:
            qs = qs.filter(date_start__gte=date_from)
        if date_to:
            qs = qs.filter(date_start__lte=date_to)
        qs = _apply_id_filters(
            qs,
            request.GET.getlist("event_type"),
            request.GET.getlist("discipline"),
            request.GET.getlist("direction"),
        )
        qs = _apply_favorite_filter(qs, request)

        by_path = {loc.path: loc for loc in Location.objects.filter(is_deleted=False)}
        step = Location.steplen
        groups: dict = {}
        for comp in qs.order_by("date_start"):
            base = by_path.get(comp.location.path, comp.location)
            display = map_display_node(base, by_path, step)
            if display is None:
                continue  # nothing in the ancestry has coordinates - cannot place it
            group = groups.get(display.pk)
            if group is None:
                group = groups[display.pk] = {
                    "location_id": display.pk,
                    "name": display.name,
                    "lat": float(display.lat),
                    "lng": float(display.lng),
                    "competitions": [],
                }
            group["competitions"].append(
                {
                    "id": comp.id,
                    "title": comp.title,
                    "url": reverse("competition_detail", args=[comp.id]),
                    "date_start": comp.date_start.isoformat(),
                    "date_end": comp.date_end.isoformat() if comp.date_end else None,
                }
            )
        return JsonResponse(list(groups.values()), safe=False)


def _can_manage_token(user, competition) -> bool:
    """Who may see and manage a competition's upload token: its submitter, or an admin+/superuser.

    Kept in sync with the ``show_upload_token`` gate: the token is a secret credential, so only the
    people it is shown to may regenerate or delete it.
    """
    from registrations.views import can_manage

    return bool(getattr(user, "is_authenticated", False)) and (
        can_manage(user, competition) or user == competition.submitted_by
    )


class CompetitionDetailView(View):
    def get(self, request, pk):
        from registrations.views import can_manage

        competition = get_object_or_404(
            Competition.objects.select_related("submitted_by").prefetch_related("disciplines__category"),
            pk=pk,
        )
        from django.http import Http404

        if competition.is_deleted:
            raise Http404
        is_manager = can_manage(request.user, competition)
        can_moderate = _is_organizer_plus(request.user)
        is_author = request.user.is_authenticated and request.user == competition.submitted_by
        if competition.status != Competition.Status.APPROVED:
            # A not-yet-approved competition is visible to moderators (any organizer+) and to its
            # author (so they can track their submission and read a rejection reason); everyone
            # else gets a 404. Approve/reject buttons stay moderator-only (see can_moderate below).
            if not (can_moderate or is_author):
                raise Http404
        elif competition.is_hidden and not is_manager:
            raise Http404
        protocols = competition.protocols.all()
        # upload_token is a secret credential: only show it to the submitter or to users
        # who can manage this specific competition (superuser, admin+, or the organizer
        # who submitted it). Removed the broad rank >= ORGANIZER check that exposed
        # tokens of other organizers' competitions.
        show_upload_token = _can_manage_token(request.user, competition)
        already_registered = False
        if request.user.is_authenticated:
            from registrations.models import CompetitionRegistration

            already_registered = CompetitionRegistration.objects.filter(
                competition=competition, user=request.user
            ).exists()
        from django.conf import settings

        comments = competition.comments.select_related("author")
        can_comment = request.user.is_authenticated and (
            request.user.is_superuser
            or request.user.get_role_rank() >= User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
        )
        ctx: dict = {
            "competition": competition,
            "protocols": protocols,
            "show_upload_token": show_upload_token,
            "is_manager": is_manager,
            # The author (any role) may edit/delete/resubmit their own submission (#200); Hide and
            # the upload token stay manager-only via is_manager.
            "can_edit": is_manager or is_author,
            "already_registered": already_registered,
            "site_base_url": getattr(settings, "SITE_BASE_URL", ""),
            "comments": comments,
            "can_comment": can_comment,
            "comment_form": AddCompetitionCommentForm() if can_comment else None,
            "user_can_delete_comment": is_manager,
            "is_favorited": request.user.is_authenticated
            and CompetitionFavorite.objects.filter(user=request.user, competition=competition).exists(),
            # Approve/reject is offered only to moderators (organizer+) and only while pending.
            "can_moderate": can_moderate and competition.status == Competition.Status.PENDING_APPROVAL,
            "reject_form": RejectCompetitionForm(),
        }
        # Resolve the map pin: a venue with its own coordinates, else the nearest visible ancestor
        # (city -> region -> country). The hidden "other location" placeholder carries no coordinates,
        # so map_display_node resolves it up to the real place instead of showing nothing.
        loc = competition.location
        display = None
        if loc is not None:
            by_path = {node.path: node for node in [*loc.get_ancestors(), loc]}
            display = map_display_node(loc, by_path, Location.steplen)
        if display is not None:
            lat = float(display.lat)
            lng = float(display.lng)
            ctx["location_lat"] = f"{lat:.6f}"
            ctx["location_lng"] = f"{lng:.6f}"
            lat_dir = _("N") if lat >= 0 else _("S")
            lng_dir = _("E") if lng >= 0 else _("W")
            ctx["location_lat_display"] = f"{abs(lat):.6f}\u00b0 {lat_dir}"
            ctx["location_lng_display"] = f"{abs(lng):.6f}\u00b0 {lng_dir}"
        return render(request, "calendar_app/detail.html", ctx)


def _validate_deadline(form, reg_form, date_start, date_end):
    """Add error to reg_form if registration_deadline exceeds the competition end date."""
    deadline = reg_form.cleaned_data.get("registration_deadline")
    if not deadline:
        return True
    max_date = date_end if date_end else date_start
    # deadline is a datetime; compare its calendar day (in the active timezone) to the event date.
    deadline_date = timezone.localtime(deadline).date() if timezone.is_aware(deadline) else deadline.date()
    if deadline_date > max_date:
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
    deadline = cd.get("registration_deadline")
    # The datetime-local field yields a naive datetime; interpret it in the active timezone.
    if deadline and timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline)
    comp.registration_deadline = deadline
    comp.max_participants = cd.get("max_participants")
    comp.show_unapproved_in_list = cd.get("show_unapproved_in_list", False) if comp.require_approval else False
    comp.show_unpaid_in_list = cd.get("show_unpaid_in_list", False) if comp.require_payment else False
    comp.show_approval_status_col = cd.get("show_approval_status_col", False) if comp.require_approval else False
    comp.show_payment_status_col = cd.get("show_payment_status_col", False) if comp.require_payment else False
    comp.additional_info_mode = cd.get("additional_info_mode") or Competition.AdditionalInfoMode.FREE
    comp.show_additional_info_in_list = cd.get("show_additional_info_in_list", True)
    comp.additional_info_required = cd.get("additional_info_required", False)
    comp.relay_enabled = cd.get("relay_enabled", False)
    comp.relay_max_members = cd.get("relay_max_members") or 10
    if reg_enabled and not comp.registration_mode_locked:
        comp.registration_mode_locked = True


def _save_categories(comp, reg_form, is_organizer_plus):  # noqa: C901
    if not is_organizer_plus:  # categories are part of registration config -> organizer-only (#200)
        return
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

    def _discipline_context(self, user, form):
        return {
            **_discipline_picker_context(form),
            "locations_data": _get_locations_data(user),
        }

    def get(self, request):
        form = SubmitCompetitionForm(user=request.user)
        reg_form = RegistrationSettingsForm()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "reg_form": reg_form,
                "is_organizer_plus": self._is_organizer_plus(request.user),
                **self._discipline_context(request.user, form),
            },
        )

    def post(self, request):
        form = SubmitCompetitionForm(request.POST, request.FILES, user=request.user)
        reg_form = RegistrationSettingsForm(request.POST)
        is_organizer = self._is_organizer_plus(request.user)
        if form.is_valid() and (not is_organizer or reg_form.is_valid()):
            cd = form.cleaned_data
            if is_organizer and not _validate_deadline(form, reg_form, cd["date_start"], cd.get("date_end")):
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "reg_form": reg_form,
                        "is_organizer_plus": is_organizer,
                        **self._discipline_context(request.user, form),
                    },
                )
            try:
                # Resolve, lock and re-validate the location, then save the competition in one
                # transaction so a concurrent delete/level-change of the venue can't bind this
                # competition to a removed node or a non-venue (review: competition-create vs delete).
                with transaction.atomic():
                    location = _resolve_competition_location(cd, request.user, approved=is_organizer)
                    location = lock_competition_location(
                        location, request.user, is_admin=_can_manage_any_competition(request.user)
                    )
                    comp = Competition(
                        title_ru=cd["title_ru"],
                        title_kk=cd.get("title_kk", ""),
                        title_en=cd.get("title_en", ""),
                        description_ru=cd.get("description_ru", ""),
                        description_kk=cd.get("description_kk", ""),
                        description_en=cd.get("description_en", ""),
                        event_type=cd.get("event_type"),
                        location=location,
                        date_start=cd["date_start"],
                        date_end=cd.get("date_end"),
                        url_announcement=cd.get("url_announcement", ""),
                        url_registration=cd.get("url_registration", ""),
                        url_route=cd.get("url_route", ""),
                        url_regulations=cd.get("url_regulations", ""),
                        url_results=cd.get("url_results", ""),
                        submitted_by=request.user,
                    )
                    for fname in ("file_announcement", "file_route", "file_regulations", "file_results"):
                        f = cd.get(fname)
                        if f:
                            setattr(comp, fname, f)
                    # An organizer's own submission is published straight away -- but not onto
                    # geography still awaiting review: that would put the pending city's name on a
                    # public page and leave the branch holding an approved event, which is what
                    # makes it impossible to reject afterwards.
                    # Only ancestors matter, as everywhere else: an organizer's own start-point
                    # venue under an approved city is fine and stays published.
                    if is_organizer and chain_is_approved(
                        comp.location.get_parent() if comp.location is not None else None
                    ):
                        comp.status = Competition.Status.APPROVED
                        comp.approved_by = request.user
                        comp.approved_at = timezone.now()
                        _apply_registration_settings(comp, reg_form, True)
                    else:
                        comp.status = Competition.Status.PENDING_APPROVAL
                        comp.registration_enabled = False
                    comp.save()
                    comp.disciplines.set(cd.get("disciplines") or [])
                    if is_organizer and reg_form.is_valid():
                        _save_categories(comp, reg_form, True)
            except LocationConflictError:
                form.add_error("location", _("This location is not available."))
            else:
                return redirect("calendar_list")
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "reg_form": reg_form,
                "is_organizer_plus": is_organizer,
                **self._discipline_context(request.user, form),
            },
        )


class EditCompetitionView(View):
    template_name = "calendar_app/edit.html"

    def _get_competition_or_403(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk, is_deleted=False)
        from registrations.views import can_manage_or_own

        if not can_manage_or_own(request.user, comp):
            raise PermissionDenied
        return comp

    def get(self, request, pk):
        comp = self._get_competition_or_403(request, pk)
        form = SubmitCompetitionForm(
            initial={
                "title_ru": comp.title_ru or "",
                "title_kk": comp.title_kk or "",
                "title_en": comp.title_en or "",
                "description_ru": comp.description_ru or "",
                "description_kk": comp.description_kk or "",
                "description_en": comp.description_en or "",
                "event_type": comp.event_type_id,
                "disciplines": list(comp.disciplines.values_list("pk", flat=True)),
                "location": comp.location_id,
                "date_start": comp.date_start,
                "date_end": comp.date_end,
                "url_announcement": comp.url_announcement,
                "url_registration": comp.url_registration,
                "url_route": comp.url_route,
                "url_regulations": comp.url_regulations,
                "url_results": comp.url_results,
            },
            user=request.user,
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
                "additional_info_mode": comp.additional_info_mode,
                "show_additional_info_in_list": comp.show_additional_info_in_list,
                "additional_info_required": comp.additional_info_required,
                "relay_enabled": comp.relay_enabled,
                "relay_max_members": comp.relay_max_members,
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
        disc_ctx = {
            **_discipline_picker_context(form),
            "locations_data": _get_locations_data(request.user),
            "initial_location_id": comp.location_id or "",
        }
        return render(
            request,
            self.template_name,
            {
                "competition": comp,
                "form": form,
                "reg_form": reg_form,
                "categories_json": json.dumps(categories),
                "mode_locked": comp.registration_mode_locked,
                **disc_ctx,
            },
        )

    def post(self, request, pk):
        comp = self._get_competition_or_403(request, pk)
        form = SubmitCompetitionForm(request.POST, request.FILES, user=request.user)
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
                        **_discipline_picker_context(form),
                        "locations_data": _get_locations_data(request.user),
                        "initial_location_id": form["location"].value() or "",
                    },
                )
            comp.title_ru = cd["title_ru"]
            comp.title_kk = cd.get("title_kk", "")
            comp.title_en = cd.get("title_en", "")
            comp.description_ru = cd.get("description_ru", "")
            comp.description_kk = cd.get("description_kk", "")
            comp.description_en = cd.get("description_en", "")
            comp.event_type = cd.get("event_type")
            comp.date_start = cd["date_start"]
            comp.date_end = cd.get("date_end")
            comp.url_announcement = cd.get("url_announcement", "")
            comp.url_registration = cd.get("url_registration", "")
            comp.url_route = cd.get("url_route", "")
            comp.url_regulations = cd.get("url_regulations", "")
            comp.url_results = cd.get("url_results", "")
            for fname in ("file_announcement", "file_route", "file_regulations", "file_results"):
                f = cd.get(fname)
                if f:
                    setattr(comp, fname, f)
            # Registration config (enable, categories, ...) stays organizer-only even when the author
            # editing their own submission is a participant (#200) -- mirror the submit view.
            is_org = _is_organizer_plus(request.user)
            _apply_registration_settings(comp, reg_form, is_org)
            try:
                # Resolve, lock and re-validate the location, then save in one transaction so a
                # concurrent delete/level-change of the venue can't bind this competition to a
                # removed node or a non-venue (review: competition-update vs delete).
                with transaction.atomic():
                    location = _resolve_competition_location(cd, request.user, approved=is_org)
                    comp.location = lock_competition_location(
                        location, request.user, is_admin=_can_manage_any_competition(request.user)
                    )
                    _unpublish_if_geography_is_pending(comp, request.user)
                    comp.save()
                    comp.disciplines.set(cd.get("disciplines") or [])
                    _save_categories(comp, reg_form, is_org)
            except LocationConflictError:
                form.add_error("location", _("This location is not available."))
            else:
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
        disc_ctx = {
            **_discipline_picker_context(form),
            "locations_data": _get_locations_data(request.user),
            "initial_location_id": comp.location_id or "",
        }
        return render(
            request,
            self.template_name,
            {
                "competition": comp,
                "form": form,
                "reg_form": reg_form,
                "categories_json": json.dumps(categories, default=str),
                "mode_locked": comp.registration_mode_locked,
                **disc_ctx,
            },
        )


class ModerationView(OrganizerRequiredMixin, TemplateView):
    template_name = "calendar_app/moderate.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["competitions"] = (
            Competition.objects.filter(status=Competition.Status.PENDING_APPROVAL, is_deleted=False)
            .select_related("submitted_by", "event_type", "location")
            .prefetch_related("disciplines__category")
            .order_by("date_start")
        )
        context["reject_form"] = RejectCompetitionForm()
        if _can_manage_any_competition(self.request.user):
            context["pending_locations"] = (
                Location.objects.filter(proposal__status=LocationProposal.Status.PENDING_APPROVAL, is_deleted=False)
                .select_related("proposal__submitted_by")
                .order_by("path")
            )
        return context


def _safe_next(request, default_view: str) -> str:
    """Return the POSTed ``next`` URL when it is a safe same-host path, else the ``default_view``.

    Approve/reject can be triggered from the moderation queue or from a competition's own page, so
    each form posts where to return to; an unsafe/foreign ``next`` falls back to the default.
    """
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return reverse(default_view)


class ApproveCompetitionView(OrganizerRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import LocationPendingError

        comp = get_object_or_404(Competition, pk=pk, status=Competition.Status.PENDING_APPROVAL, is_deleted=False)
        try:
            comp.approve(reviewer=request.user)
        except LocationPendingError:
            messages.error(
                request,
                _("This event's location is still awaiting review; an administrator must approve it first."),
            )
        return redirect(_safe_next(request, "calendar_moderate"))


class RejectCompetitionView(OrganizerRequiredMixin, View):
    def post(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk, status=Competition.Status.PENDING_APPROVAL, is_deleted=False)
        form = RejectCompetitionForm(request.POST)
        if not form.is_valid():
            # A rejection reason is required, so an empty one is refused rather than silently
            # rejecting without an explanation the author would then see.
            messages.error(request, _("Please provide a reason for rejection."))
            return redirect(_safe_next(request, "calendar_moderate"))
        try:
            comp.reject(reviewer=request.user, reason=form.cleaned_data["rejection_reason"])
        except ValueError:
            pass
        return redirect(_safe_next(request, "calendar_moderate"))


class AddCompetitionCommentView(ParticipantRequiredMixin, View):
    def post(self, request, competition_pk):
        from django.http import Http404

        from registrations.views import can_manage as _can_manage

        competition = get_object_or_404(
            Competition, pk=competition_pk, status=Competition.Status.APPROVED, is_deleted=False
        )
        if competition.is_hidden and not _can_manage(request.user, competition):
            raise Http404
        form = AddCompetitionCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.competition = competition
            comment.author = request.user
            comment.save()
        else:
            first_errors = next(iter(form.errors.values()), [])
            error = first_errors[0] if first_errors else _("Invalid submission.")
            messages.error(request, error)
        return redirect("competition_detail", pk=competition_pk)


class ToggleFavoriteView(LoginRequiredMixin, View):
    """Toggle the signed-in user's favorite mark on a competition (issue #183).

    Progressive enhancement: the star on the detail page posts here. A fetch() request (sending the
    ``X-Requested-With`` header) gets JSON ``{"favorited": bool}`` back so the star can update in
    place; a plain form submit (no JS) toggles and redirects to the detail page.
    """

    def post(self, request, pk):
        from django.http import Http404

        from registrations.views import can_manage as _can_manage

        competition = get_object_or_404(Competition, pk=pk, status=Competition.Status.APPROVED, is_deleted=False)
        if competition.is_hidden and not _can_manage(request.user, competition):
            raise Http404
        favorite, created = CompetitionFavorite.objects.get_or_create(user=request.user, competition=competition)
        if not created:
            favorite.delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"favorited": created})
        return redirect("competition_detail", pk=pk)


class DeleteCompetitionCommentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(CompetitionComment.objects.select_related("competition__submitted_by"), pk=pk)
        from registrations.views import can_manage

        if not can_manage(request.user, comment.competition):
            raise PermissionDenied
        competition_pk = comment.competition_id
        comment.delete()
        return redirect("competition_detail", pk=competition_pk)


class CompetitionDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from registrations.views import can_manage_or_own

        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, competition):
            raise PermissionDenied
        competition.is_deleted = True
        competition.save(update_fields=["is_deleted"])
        return redirect("calendar_list")


class ResubmitCompetitionView(LoginRequiredMixin, View):
    """The author sends a rejected competition back for a fresh review (#200)."""

    def post(self, request, pk):
        from registrations.views import can_manage_or_own

        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, competition):
            raise PermissionDenied
        try:
            competition.resubmit()
        except ValueError:
            messages.error(request, _("Only a rejected competition can be resubmitted."))
        else:
            messages.success(request, _("Your competition was sent for review again."))
        return redirect("competition_detail", pk=pk)


class CompetitionHideView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from registrations.views import can_manage

        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage(request.user, competition):
            raise PermissionDenied
        competition.is_hidden = not competition.is_hidden
        competition.save(update_fields=["is_hidden"])
        return redirect("competition_detail", pk=pk)


class RegenerateUploadTokenView(LoginRequiredMixin, View):
    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not _can_manage_token(request.user, competition):
            raise PermissionDenied
        competition.upload_token = uuid.uuid4()
        competition.save(update_fields=["upload_token"])
        messages.success(request, _("Timing token regenerated. The previous token no longer works."))
        return redirect("competition_detail", pk=pk)


class DeleteUploadTokenView(LoginRequiredMixin, View):
    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not _can_manage_token(request.user, competition):
            raise PermissionDenied
        competition.upload_token = None
        competition.save(update_fields=["upload_token"])
        messages.success(request, _("Timing token deleted. Timing tools can no longer access this competition."))
        return redirect("competition_detail", pk=pk)
