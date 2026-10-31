import datetime
import functools
import json
import uuid
from calendar import monthrange

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View
from modeltranslation.utils import build_localized_fieldname

from accounts import managing, roles
from accounts.access import ParticipantRequiredMixin
from accounts.models import User
from assistant.conversations import link as link_conversation
from cycling_site.setup_hints import sign_in_url
from locations.maps import map_links
from locations.models import (
    Location,
    LocationConflictError,
    LocationProposal,
    chain_is_approved,
    deepest_chosen,
    lock_competition_location,
    map_display_node,
    places_seen_by,
    sort_locations_for_filter,
)

from .forms import (
    AddCompetitionCommentForm,
    CompetitionFilterForm,
    CompetitionMaterialFormSet,
    RegistrationSettingsForm,
    RejectCompetitionForm,
    ReportCompetitionForm,
    SubmitCompetitionForm,
)
from .guest_region import OFFERED_COOKIE, guest_region
from .listing_seo import describe_filters, index_policy, landing_filters
from .models import (
    Competition,
    CompetitionComment,
    CompetitionFavorite,
    CompetitionInvite,
    CompetitionReport,
    Discipline,
    DisciplineCategory,
    EventType,
)
from .seo import sports_event
from .visibility import can_manage_or_own, can_open, can_review, can_see, listed_for, manages, public_events


def _get_locations_data(user=None) -> list:
    """Approved Location nodes (+ the given user's own pending proposals) in 3 languages.

    Includes hidden depth-4 fallback venue nodes so that JS can use them for
    auto-assignment when no real venue is selected. Pending locations are visible
    only to the user who proposed them, so they can pick their own before approval.
    """
    # Public = no proposal or an approved one; a pending proposal is visible only to its proposer.
    visible = places_seen_by(user)
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
        and not roles.at_least(user, roles.APPROVE_PLACES)
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
            name_kk=(cd.get("new_venue_name_kk") or "").strip(),
            name_en=(cd.get("new_venue_name_en") or "").strip(),
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
    """Union of descendant pks (incl. self) for the deepest of the given location ids."""
    ids = _parse_int_ids(location_ids)
    if not ids:
        return set()
    pks: set[int] = set()
    for loc in deepest_chosen(ids):
        pks.update(loc.get_descendants(include_self=True).values_list("pk", flat=True))
    return pks


def _apply_id_filters(qs, event_type_ids, discipline_ids, direction_ids):
    """Apply integer-keyed multi-select filters; non-integer values are ignored.

    Each argument is a list of GET values (each value may itself be a comma-joined
    group of ids). Chosen disciplines win over directions, as a city does over its country: with
    any discipline in the query a competition matches by its disciplines alone, and the directions
    only say which disciplines the picker offers (the page keeps them in the address so their boxes
    stay ticked); without one, it matches by a discipline in a chosen direction. Both
    ``event_types`` and ``disciplines`` are many-to-many, so each join is de-duplicated -- without
    that a race carrying two of the selected values would be listed twice.
    """
    event_types = _parse_int_ids(event_type_ids)
    if event_types:
        qs = qs.filter(event_types__id__in=event_types).distinct()
    disciplines = _parse_int_ids(discipline_ids)
    directions = _parse_int_ids(direction_ids)
    if disciplines:
        qs = qs.filter(disciplines__in=disciplines).distinct()
    elif directions:
        qs = qs.filter(disciplines__category_id__in=directions).distinct()
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


class ModeratorRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not roles.at_least(request.user, roles.MODERATE_EVENTS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _user_filter_default_params(user) -> list:
    """(param, id) pairs reproducing the user's saved calendar-filter preferences (issue #229).

    Directions go as ``discipline_category`` and disciplines as ``discipline`` -- the same names the
    filter widgets restore from -- so the redirect below reconstructs exactly the saved selection.
    """
    if not getattr(user, "is_authenticated", False):
        return []
    # The direction filter merges same-name disciplines across categories into one checkbox (e.g.
    # "Relay" lives under 11 directions), so a saved discipline stands in for all its same-name
    # siblings. Expand to that merged group (matching a name in any locale), so the redirect
    # reproduces exactly what the widget round-trips; the directions go along whole, and the
    # disciplines win over them on every page, as they do when picked by hand.
    names = {n for d in user.preferred_disciplines.all() for n in (d.name_ru, d.name_kk, d.name_en) if n}
    merged = (
        Discipline.objects.filter(Q(name_ru__in=names) | Q(name_kk__in=names) | Q(name_en__in=names))
        if names
        else Discipline.objects.none()
    )
    discipline_ids = list(merged.order_by("pk").values_list("pk", flat=True))
    pairs = [("discipline_category", pk) for pk in user.preferred_directions.values_list("pk", flat=True)]
    pairs += [("discipline", pk) for pk in discipline_ids]
    pairs += [("location", pk) for pk in user.preferred_locations.values_list("pk", flat=True)]
    pairs += [("event_type", pk) for pk in user.preferred_event_types.values_list("pk", flat=True)]
    return pairs


class DefaultFilterRedirectMixin:
    """Open a filter page (calendar/list/map) with the user's saved preferences pre-applied.

    Fires only on a fresh visit -- a request with no query string at all. Once any param is present
    (including after the user clears the filter, which still submits the date range), the page is
    left exactly as asked, so the default is a starting point the user can always override or empty.
    Users without saved preferences are unaffected (issue #229). A guest opens on their own region
    instead, once a visit (calendar_app.guest_region, issue #332).
    """

    def get(self, request, *args, **kwargs):
        if not request.GET:
            pairs = _user_filter_default_params(request.user)
            if pairs:
                return redirect(f"{request.path}?{urlencode(pairs)}")
            region = guest_region(request)
            if region is not None:
                response = redirect(f"{request.path}?{urlencode([('location', region.pk)])}")
                # For the visit only: a guest who clears the region keeps the whole calendar after it.
                response.set_cookie(OFFERED_COOKIE, "1", samesite="Lax", secure=request.is_secure(), httponly=True)
                # It depends on where the guest is, which no address or cache key carries: no shared cache
                # may hand one guest's region to the next.
                patch_cache_control(response, private=True, no_store=True)
                return response
        return super().get(request, *args, **kwargs)


def upcoming_competitions(user, limit: int = 20) -> list[Competition]:
    """The next events, as plain rows.

    The grid draws itself from JSON after the page loads, so a crawler that does not run
    scripts sees a calendar with nothing in it. These rows are rendered into the page itself,
    which gives every event a link that can be followed from /calendar/ -- and gives a reader
    on a slow connection something to read before the grid appears.
    """
    today = timezone.localdate()
    return list(
        # Hidden stays out for everybody, admins too: these rows carry no "hidden" badge, and they
        # are what a crawler reads. Invite-only rows are the reader's own business.
        listed_for(
            Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False, is_hidden=False), user
        )
        # A stage race that started yesterday and ends on Sunday is still ahead of the reader,
        # and dropping it the morning after day one is how a multi-day event disappears mid-race.
        .filter(Q(date_start__gte=today) | Q(date_end__gte=today))
        .select_related("location")
        .order_by("-is_top", "date_start", "pk")[:limit]
    )


#: The month names the picker offers. They are the same twelve strings the grid's own title is
#: built from, so a reader never sees two spellings of the same month on one page.
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def calendar_year_choices() -> list[int]:
    """Every year the month picker can jump to, on the calendar, the list and the map alike.

    The arrows move one month per click, so reaching a race from six years ago meant seventy clicks
    on `prev`. The years span the events the site actually holds, and always include the current
    one -- an empty calendar still offers this year.
    """
    from django.db.models import Max, Min

    bounds = public_events().aggregate(first=Min("date_start"), last=Max("date_start"), last_end=Max("date_end"))
    years = [timezone.localdate().year]
    years += [when.year for when in bounds.values() if when]
    return list(range(min(years), max(years) + 1))


class ListingIndexMixin:
    """Tell search engines which calendar pages are pages (listing_seo.index_policy).

    The answer travels as an X-Robots-Tag header, not a meta tag, so a skin with its own base.html
    cannot lose it.
    """

    is_list = False

    def index_context(self, context, count=None, page_number=1):
        canonical_path, noindex = index_policy(self.request, is_list=self.is_list, count=count, page_number=page_number)
        if canonical_path:
            context["canonical_path"] = canonical_path
            context["canonical_url"] = self.request.build_absolute_uri(canonical_path)
        context["robots_noindex"] = noindex

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        if context.get("robots_noindex"):
            response["X-Robots-Tag"] = "noindex"
        return response


def overlapping(qs, date_from: datetime.date | None, date_to: datetime.date | None):
    """The events of ``qs`` that run on any day from ``date_from`` to ``date_to``, either end open.

    A race from Friday to Sunday is a weekend race, and one that began last week is still on: the list
    and the map show what the calendar's grid shows (issue #352), which asks FullCalendar's range the
    same way with its end excluded.
    """
    if date_from is not None:
        qs = qs.filter(Q(date_end__gte=date_from) | Q(date_end__isnull=True, date_start__gte=date_from))
    if date_to is not None:
        qs = qs.filter(date_start__lte=date_to)
    return qs


def end_of_month(day: datetime.date) -> datetime.date:
    """The last day of the month `day` falls in."""
    return day.replace(day=monthrange(day.year, day.month)[1])


def map_home_area(location_ids) -> list | None:
    """The corners of the area in settings.MAP_HOME_AREAS that holds every chosen place, if one does.

    A place counts by its own point; one without coordinates says nothing. No place, a place outside
    every area, or places in two areas -- the map fits its events instead.
    """
    points = [
        (float(loc.lat), float(loc.lng))
        for loc in deepest_chosen(location_ids)
        if loc.lat is not None and loc.lng is not None
    ]
    if not points:
        return None
    for (south, west), (north, east) in settings.MAP_HOME_AREAS.values():
        if all(south <= lat <= north and west <= lng <= east for lat, lng in points):
            return [[south, west], [north, east]]
    return None


def month_picker_choices() -> dict:
    """The words and years the period row above the calendar, the list and the map is built from."""
    return {
        "calendar_months": list(enumerate((_(name) for name in MONTH_NAMES), start=1)),
        "calendar_years": calendar_year_choices(),
        "calendar_date_words": calendar_date_words(),
        "calendar_week": {"first_day": settings.CALENDAR_FIRST_WEEKDAY, "weekend": list(settings.CALENDAR_WEEKEND)},
    }


def calendar_date_words() -> dict:
    """Month and weekday names the calendar script writes dates with, in the reader's language.

    FullCalendar leans on the browser's Intl for these, and browsers do not agree on Kazakh: some
    write "2026 M10 1 THU" for a day heading. Django's own catalogues do, so the script borrows
    them -- months in the form a date takes (the Russian genitive), weekdays from Monday.

    Inside a date Russian and Kazakh write both in lower case, while the catalogues give the
    weekdays, and Kazakh the months too, capitalised as they stand alone.
    English keeps its capitals.
    """
    from django.utils.formats import date_format
    from django.utils.translation import get_language

    monday = datetime.date(2001, 1, 1)
    months = [date_format(datetime.date(2001, month, 1), "E") for month in range(1, 13)]
    weekdays = [date_format(monday + datetime.timedelta(days=day), "l") for day in range(7)]
    weekday_short = [date_format(monday + datetime.timedelta(days=day), "D") for day in range(7)]
    if not (get_language() or "").startswith("en"):
        months = [month.lower() for month in months]
        weekdays = [weekday.lower() for weekday in weekdays]
    return {
        "months": months,
        "weekdays": weekdays,
        "weekday_short": weekday_short,
        "year_first": (get_language() or "").startswith("kk"),
    }


@functools.lru_cache(maxsize=8)
def _months_in(language: str) -> tuple[str, ...]:
    """``calendar_date_words``' months for ``language``, the language active when it is asked."""
    return tuple(calendar_date_words()["months"])


def date_range_words(start, end=None) -> str:
    """An event's days in the words the period line names them in (the interface skill, rule 12):
    "24 October 2026", "24-25 October 2026", "30 September - 2 October 2026", and both years when
    the days cross into a new one -- the month in its Russian case, the year first in Kazakh, an en
    dash between. The period line builds the same words in the browser (``label()`` in
    ``_period_nav.html``): a change to one belongs in the other.
    """
    language = get_language() or ""
    months = _months_in(language)

    def with_year(text, year):
        return f"{year} {text}" if language.startswith("kk") else f"{text} {year}"

    def day(d):
        return f"{d.day} {months[d.month - 1]}"

    if not end or end <= start:
        return with_year(day(start), start.year)
    if end.year != start.year:
        return f"{with_year(day(start), start.year)} \u2013 {with_year(day(end), end.year)}"
    if end.month == start.month:
        return with_year(f"{start.day}\u2013{day(end)}", start.year)
    return with_year(f"{day(start)} \u2013 {day(end)}", start.year)


def day_groups(rows) -> list[dict]:
    """A list page's rows under their first day, for the list of days a phone shows (issue #330).

    Each day is headed as the calendar heads it ("22 October, Thursday"), from the same catalogue
    words; a race over several days stands once, on its first day, with the day it ends.
    """
    words = calendar_date_words()

    def label(day):
        return f"{day.day} {words['months'][day.month - 1]}"

    groups: list[dict] = []
    # Top events come first in the list (and first among its rows); they go under a heading of
    # their own, each with its dates, before the days -- the same divider the table draws.
    top = [comp for comp in rows if comp.is_top]
    if top:
        groups.append({"date": None, "label": _("Top events"), "top": True, "rows": []})
        for comp in top:
            when = label(comp.date_start)
            if comp.date_end and comp.date_end > comp.date_start:
                when = f"{when} \u2013 {label(comp.date_end)}"
            groups[-1]["rows"].append({"comp": comp, "until": "", "when": when})
    for comp in rows:
        if comp.is_top:
            continue
        day = comp.date_start
        if not groups or groups[-1]["date"] != day:
            groups.append({"date": day, "label": f"{label(day)}, {words['weekdays'][day.weekday()]}", "rows": []})
        until = label(comp.date_end) if comp.date_end and comp.date_end > day else ""
        groups[-1]["rows"].append({"comp": comp, "until": until})
    return groups


class CalendarView(ListingIndexMixin, DefaultFilterRedirectMixin, TemplateView):
    template_name = "calendar_app/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.index_context(context)
        context["upcoming"] = upcoming_competitions(self.request.user)
        # Links to the filtered lists worth being pages of their own, so a crawler (and a reader
        # scanning for their own city) can reach them without building a filter first.
        regions, places, kinds = landing_filters(limit_places=24, limit_kinds=12, limit_regions=12)
        context["landing_regions"] = regions
        context["landing_places"] = places
        context["landing_kinds"] = kinds
        context["event_types"] = EventType.objects.all()
        context["discipline_categories"] = DisciplineCategory.objects.all()
        context["event_types_json"] = _event_types_for_locale()
        context["categories_json"] = _categories_for_locale()
        context["disciplines_json"] = _disciplines_for_locale()
        context["only_favorite"] = _only_favorite_requested(self.request)
        context.update(month_picker_choices())
        return context


class LocationsDataView(View):
    """The location tree the filter cascade is built from, as its own cacheable response.

    It used to be inlined into every calendar page: a megabyte of JSON on the two addresses that
    are loaded and crawled most. Served separately it is fetched once and then answered from the
    browser cache, and the page itself becomes small enough to read.
    """

    #: Ten minutes. The tree changes when a venue is approved, and a filter list that is a few
    #: minutes behind costs nothing; a fresh copy on every page load costs a megabyte.
    MAX_AGE = 600

    #: The same query and the same megabyte of JSON for everyone, so it is built once per worker
    #: rather than once per visitor. Half the browser's lifetime, so nobody holds a copy older
    #: than MAX_AGE by much.
    SERVER_CACHE_SECONDS = 300
    CACHE_KEY = "calendar:locations-tree"

    def get(self, request):
        from django.core.cache import cache

        payload = cache.get(self.CACHE_KEY)
        if payload is None:
            payload = json.dumps(_get_locations_data(), cls=DjangoJSONEncoder)
            cache.set(self.CACHE_KEY, payload, self.SERVER_CACHE_SECONDS)
        response = HttpResponse(payload, content_type="application/json")
        response["Cache-Control"] = f"public, max-age={self.MAX_AGE}"
        return response


class CalendarEventsAPIView(View):
    def get(self, request):
        from django.db.models import Q

        qs = (
            Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False)
            .prefetch_related("event_types")
            .prefetch_related("disciplines__category")
        )
        qs = listed_for(qs, request.user)
        # The grid sends ISO datetimes; a value that is not a date is dropped, as the list's filters drop it.
        start = _parse_date((request.GET.get("start") or "")[:10], None)
        end = _parse_date((request.GET.get("end") or "")[:10], None)
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
                    "event_type": comp.event_type_label,
                    "discipline": comp.disciplines_label,
                    "favorite": comp.pk in favorited_ids,
                    # The grid puts a top event first in its day (eventOrder in calendar.html).
                    "top": comp.is_top,
                },
            }
            for comp in competitions
        ]
        return JsonResponse(events, safe=False)


class CompetitionListView(ListingIndexMixin, DefaultFilterRedirectMixin, TemplateView):
    template_name = "calendar_app/list.html"
    is_list = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(month_picker_choices())
        form = CompetitionFilterForm(self.request.GET or None)
        today = timezone.localdate()
        date_from = today
        # A filter counts only when it names something. "?location=" -- a cleared select, a stale
        # link -- carries a value that is no id at all, and reading it as a filter both empties the
        # page and drops the date window from it.
        chosen = {
            name: _parse_int_ids(self.request.GET.getlist(name))
            for name in ("location", "discipline", "discipline_category", "event_type")
        }
        # The unfiltered list is a "what is on soon" page: the rest of this month, the period the
        # calendar and the map open on too (issue #330). A list filtered down to one city or one
        # discipline is a page about that city -- and two rows of it is not a page about anything,
        # so the whole season ahead stands. An explicit date_to from the reader still wins over both.
        faceted = any(chosen.values())
        date_to = None if faceted and self.request.GET.get("period") != "month" else end_of_month(today)

        is_manager = roles.at_least(self.request.user, roles.MANAGE_ALL_EVENTS)
        qs = (
            Competition.objects.filter(status=Competition.Status.APPROVED, is_deleted=False)
            .select_related("location")
            .prefetch_related("event_types")
            .prefetch_related("disciplines__category")
        )
        qs = listed_for(qs, self.request.user)

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
        if chosen["location"]:
            qs = qs.filter(location_id__in=_location_descendant_pks(chosen["location"]))
        qs = _apply_favorite_filter(qs, self.request)

        # Top events first, then the rest by date; the page draws a divider between the two. The id
        # settles a day's events: without it the database may order them anew for every page, and
        # one event shows on two pages while another on none.
        qs = overlapping(qs, date_from, date_to).order_by("-is_top", "date_start", "pk")
        paginator = Paginator(qs, 20)
        page = paginator.get_page(self.request.GET.get("page", 1))
        context["competitions"] = page
        context["top_count"] = sum(1 for comp in page if comp.is_top)
        # The same rows by day, for a phone: a table of ten columns does not read on one.
        context["days"] = day_groups(page)
        # Pass the evaluated page rows (not the sliced queryset) so the star lookup reuses them
        # instead of re-running the paginated query as an IN subquery.
        context["favorited_ids"] = _favorited_ids(self.request, list(page))
        # Registration run on this site has no URL field for the row to show, so the row asks the
        # event. Only rows that take entries here are asked: with a participant limit the check
        # counts registrations, and the other rows would pay that query for nothing.
        context["registration_open_ids"] = {
            comp.pk for comp in page if comp.registration_enabled and comp.is_registration_open()
        }
        context["only_favorite"] = _only_favorite_requested(self.request)
        context["filter_form"] = form
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["is_manager"] = is_manager
        context["discipline_categories"] = DisciplineCategory.objects.all()
        context["event_types_json"] = _event_types_for_locale()
        context["categories_json"] = _categories_for_locale()
        context["disciplines_json"] = _disciplines_for_locale()
        # A filtered list is a page about a city or a discipline; say so, instead of leaving every
        # combination sharing one title and one site-wide description.
        meta_title, meta_description = describe_filters(
            locations={loc.pk for loc in deepest_chosen(_parse_int_ids(self.request.GET.getlist("location")))},
            disciplines=_parse_int_ids(self.request.GET.getlist("discipline")),
            event_types=_parse_int_ids(self.request.GET.getlist("event_type")),
            count=page.paginator.count,
            date_from=date_from,
            date_to=date_to,
        )
        if meta_title:
            context["meta_title"] = meta_title
            context["meta_description"] = meta_description
        self.index_context(context, count=page.paginator.count, page_number=page.number)
        return context


class CalendarMapView(ListingIndexMixin, DefaultFilterRedirectMixin, TemplateView):
    template_name = "calendar_app/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.index_context(context)
        context.update(month_picker_choices())
        today = timezone.localdate()
        context["date_from"] = _parse_date(self.request.GET.get("date_from"), today)
        context["date_to"] = _parse_date(self.request.GET.get("date_to"), end_of_month(today))
        context["event_types_json"] = _event_types_for_locale()
        context["categories_json"] = _categories_for_locale()
        context["disciplines_json"] = _disciplines_for_locale()
        context["only_favorite"] = _only_favorite_requested(self.request)
        context["map_home_area"] = map_home_area(_parse_int_ids(self.request.GET.getlist("location")))
        context["map_default_view"] = settings.MAP_DEFAULT_VIEW
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
        qs = Competition.objects.filter(
            status=Competition.Status.APPROVED,
            is_deleted=False,
            location__isnull=False,
            location__is_deleted=False,
        ).select_related("location")
        qs = listed_for(qs, request.user)
        qs = overlapping(
            qs, _parse_date(request.GET.get("date_from"), None), _parse_date(request.GET.get("date_to"), None)
        )
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
        # Top events first at each place, as everywhere else events are listed.
        for comp in qs.order_by("-is_top", "date_start", "pk"):
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
                    "when": date_range_words(comp.date_start, comp.date_end),
                }
            )
        return JsonResponse(list(groups.values()), safe=False)


def _preview_image_tags(request, competition) -> dict:
    """What a chat should show for this event, if it brought a picture of its own.

    An empty dict when it did not: the page then falls back to the site mark, which is what every
    event showed before. The size travels with the URL so a messenger can lay the card out without
    downloading the file.
    """
    image = getattr(competition, "preview_image", None)
    if not image:
        return {}
    try:
        width, height = image.width, image.height
    except (OSError, ValueError):
        # The row points at a file that is no longer on disk; the site mark is a better answer
        # than a broken picture.
        return {}
    return {
        "og_image": request.build_absolute_uri(image.url),
        "og_image_width": width,
        "og_image_height": height,
    }


def _link_preview_tags(request, competition) -> dict:
    """What a search engine and a chat read in the head of a page about this event."""
    return {
        # What a search engine reads: the event's own name and a sentence about it, instead of
        # the one site-wide line every page used to carry. A chat reads og_description below.
        "meta_title": competition.title,
        "meta_description": competition.search_summary(),
        # What a chat shows under the title: the organizer's own line in the page's language
        # when they wrote one (the meeting time and place, which the summary cannot know), else
        # the summary above, in that same language. The language's own column, not the
        # translated field: its fallback put a Russian line into a Kazakh chat, where the form
        # promises the date and the place.
        "og_description": getattr(competition, build_localized_fieldname("preview_text", get_language()), ""),
        "og_type": "article",
        # The picture a chat shows for this event. Absolute, because the messenger fetching it
        # has nothing to resolve a relative path against.
        **_preview_image_tags(request, competition),
    }


def _share_url(request, competition, *, is_public: bool, invite_url: str | None) -> str | None:
    """What an event page's share button hands out (issue #327), or None for no button.

    The page's own address when anybody can open it. For an invite-only event, its invitation link
    -- ``invite_url`` is only there for the people who may edit it, who could as well make it public.
    A hidden or not-yet-approved event, or an invitee, gets no button: the link would open for nobody
    it was sent to.
    """
    if is_public:
        return request.build_absolute_uri(competition.get_absolute_url())
    if competition.invite_only and competition.status == Competition.Status.APPROVED and not competition.is_hidden:
        return invite_url
    return None


def _moderation_history(competition) -> list[dict]:
    """The event's way through review, oldest first, as admins see it at the foot of its page (#741).

    Only what was recorded: an old event's steps may start late or miss a resubmission (see
    CompetitionStatusChange). The e-mail stands beside the name: two accounts may carry one name.
    """
    history = []
    for step in competition.status_changes.select_related("changed_by"):
        who = step.changed_by
        name = None
        if who is not None:
            full = who.get_full_name()
            name = f"{full} ({who.email})" if full and who.email else (full or who.email or who.username)
        history.append({"at": step.changed_at, "label": step.label, "by": name, "reason": step.reason})
    return history


class CompetitionDetailView(View):
    def get(self, request, pk):
        from registrations.views import can_manage

        competition = get_object_or_404(
            Competition.objects.select_related("submitted_by").prefetch_related("disciplines__category"),
            pk=pk,
        )
        if not can_open(request.user, competition):
            raise Http404
        is_manager = can_manage(request.user, competition)
        is_author = request.user.is_authenticated and request.user == competition.submitted_by
        # Any organizer moderates -- except an invite-only event, which is for the people who may
        # edit it, so only admins and up review it (see visibility.can_review).
        can_moderate = roles.at_least(request.user, roles.MODERATE_EVENTS) and (
            not competition.invite_only or roles.at_least(request.user, roles.MANAGE_ALL_EVENTS)
        )
        protocols = competition.protocols.all()
        # upload_token is a secret credential: only show it to the submitter or to users
        # who can manage this specific competition (superuser, admin+, or the organizer
        # who submitted it). Removed the broad rank >= ORGANIZER check that exposed
        # tokens of other organizers' competitions.
        show_upload_token = can_manage_or_own(request.user, competition)
        already_registered = False
        registers_others = False
        if request.user.is_authenticated:
            from registrations.models import CompetitionRegistration

            already_registered = CompetitionRegistration.objects.filter(
                competition=competition, user=request.user
            ).exists()
            # Registered oneself, one may still register the members one manages (issue #315),
            # on the page for several, which a relay does not have.
            registers_others = (
                already_registered and not competition.relay_enabled and bool(managing.member_ids(request.user))
            )

        comments = competition.comments.select_related("author")
        can_comment = roles.at_least(request.user, roles.COMMENT)
        # Reporting (issue #233): a confirmed user can flag a public event as inaccurate. Only
        # offered on approved, non-hidden events (the only ones the wider public can see).
        is_public = (
            competition.status == Competition.Status.APPROVED
            and not competition.is_hidden
            and not competition.invite_only
        )
        can_report = is_public and roles.at_least(request.user, User.Role.PARTICIPANT)  # issue #233
        already_reported = (
            request.user.is_authenticated
            and CompetitionReport.objects.filter(
                competition=competition, reported_by=request.user, resolved=False
            ).exists()
        )
        # Only admins+ act on reports (dismiss / edit / delete); show them the open reports so they
        # know what was flagged. Organizers who merely own the event are not report moderators here.
        open_reports = (
            list(competition.reports.filter(resolved=False).select_related("reported_by"))
            if roles.at_least(request.user, roles.MANAGE_ALL_EVENTS)
            else []
        )
        ctx: dict = {
            "competition": competition,
            "protocols": protocols,
            # Photo and video coverage, in the order its author arranged it. Shown to everyone who
            # can see the event at all -- the links are public pages, not a manager's business.
            "materials": competition.materials.all(),
            "show_upload_token": show_upload_token,
            "is_manager": is_manager,
            # The author (any role) may edit/delete/resubmit their own submission (#200); Hide and
            # the upload token stay manager-only via is_manager.
            "can_edit": is_manager or is_author,
            "already_registered": already_registered,
            "registers_others": registers_others,
            "site_base_url": request.build_absolute_uri("/").rstrip("/"),
            "comments": comments,
            "can_comment": can_comment,
            "comment_form": AddCompetitionCommentForm() if can_comment else None,
            "user_can_delete_comment": is_manager,
            "is_favorited": request.user.is_authenticated
            and CompetitionFavorite.objects.filter(user=request.user, competition=competition).exists(),
            # Approve/reject is offered only to moderators (organizer+) and only while pending.
            "can_moderate": can_moderate and competition.status == Competition.Status.PENDING_APPROVAL,
            "reject_form": RejectCompetitionForm(),
            "can_report": can_report,
            "already_reported": already_reported,
            "report_form": ReportCompetitionForm() if can_report else None,
            "open_reports": open_reports,
            "can_dismiss_reports": bool(open_reports),
            "moderation_history": (
                _moderation_history(competition) if roles.at_least(request.user, roles.MANAGE_ALL_EVENTS) else None
            ),
            **_link_preview_tags(request, competition),
            "structured_data": sports_event(competition, f"{request.scheme}://{request.get_host()}"),
        }
        # Resolve the map pin: a venue with its own coordinates, else the nearest visible ancestor
        # (city -> region -> country). The hidden "other location" placeholder carries no coordinates,
        # so map_display_node resolves it up to the real place instead of showing nothing.
        loc = competition.location
        display = None
        if loc is not None:
            by_path = {node.path: node for node in [*loc.get_ancestors(), loc]}
            display = map_display_node(loc, by_path, Location.steplen)
        # Links to the outside map services are a different question from the pin: they are meant to
        # be forwarded and driven to, so they are offered only for a venue's own point, never for a
        # city resolved from a venue that has none (locations.maps.start_point).
        # The name only becomes a caption on the pin, so it is the place's own name -- the full
        # country-region-city path would read as a wall of text over a single point.
        ctx["map_links"] = map_links(loc, (loc.name if loc is not None else "") or competition.title)
        if display is not None:
            lat = float(display.lat)
            lng = float(display.lng)
            ctx["location_lat"] = f"{lat:.6f}"
            ctx["location_lng"] = f"{lng:.6f}"
            lat_dir = _("N") if lat >= 0 else _("S")
            lng_dir = _("E") if lng >= 0 else _("W")
            ctx["location_lat_display"] = f"{abs(lat):.6f}\u00b0 {lat_dir}"
            ctx["location_lng_display"] = f"{abs(lng):.6f}\u00b0 {lng_dir}"
        if competition.invite_only and is_manager:
            ctx["invite_url"] = request.build_absolute_uri(
                reverse("competition_invite", args=[competition.pk, competition.invite_key])
            )
        ctx["share_url"] = _share_url(request, competition, is_public=is_public, invite_url=ctx.get("invite_url"))
        response = render(request, "calendar_app/detail.html", ctx)
        if competition.invite_only:
            # Only people let in ever reach this page, but say it plainly in case a crawler does.
            response["X-Robots-Tag"] = "noindex"
        return response


def _validate_deadline(form, reg_form, date_start, date_end):
    """Add error to reg_form if registration_deadline exceeds the competition end date."""
    deadline = reg_form.cleaned_data.get("registration_deadline")
    if not deadline:
        return True
    max_date = date_end if date_end else date_start
    # The wall-clock typed, so its day is the day at the event's place.
    if deadline.date() > max_date:
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
    # The wall-clock typed, at the event's place (issue #344): the location has to be set first.
    comp.registration_deadline = deadline.replace(tzinfo=comp.timezone) if deadline else None
    comp.max_participants = cd.get("max_participants")
    comp.show_unapproved_in_list = cd.get("show_unapproved_in_list", False) if comp.require_approval else False
    comp.show_unpaid_in_list = cd.get("show_unpaid_in_list", False) if comp.require_payment else False
    comp.show_approval_status_col = cd.get("show_approval_status_col", False) if comp.require_approval else False
    comp.show_payment_status_col = cd.get("show_payment_status_col", False) if comp.require_payment else False
    comp.additional_info_mode = cd.get("additional_info_mode") or Competition.AdditionalInfoMode.FREE
    comp.show_additional_info_in_list = cd.get("show_additional_info_in_list", True)
    comp.additional_info_required = cd.get("additional_info_required", False)
    comp.additional_info_label = (cd.get("additional_info_label") or "").strip()
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


# The prefix the coverage-links formset posts under. The edit template reads it back off the formset
# rather than repeating it, so the two cannot drift apart.
MATERIALS_PREFIX = "materials"


def _material_formset(request, comp):
    """The coverage-links formset for this request, bound only if the request actually carried one.

    An edit that never mentions the links -- no management form anywhere in the post -- is not an
    edit of the links, and leaving them alone beats failing the whole save over data the caller
    never sent. The two helpers below read an unbound formset as exactly that: nothing to say.
    """
    posted = request.method == "POST" and f"{MATERIALS_PREFIX}-TOTAL_FORMS" in request.POST
    return CompetitionMaterialFormSet(request.POST if posted else None, instance=comp, prefix=MATERIALS_PREFIX)


def _materials_are_valid(formset) -> bool:
    return not formset.is_bound or formset.is_valid()


def _save_materials(formset, comp):
    """Store the coverage links, numbering the survivors in the order the page showed them.

    The order is rewritten on every save rather than kept per row, so deleting a link from the
    middle closes the gap instead of leaving one, and a row moved by an edit lands where the editor
    put it. Rows left blank never reach here: Django drops an untouched extra form.
    """
    if not formset.is_bound:
        return
    formset.instance = comp
    formset.save(commit=False)
    for removed in formset.deleted_objects:
        removed.delete()
    position = 0
    for form in formset.forms:
        if form in formset.deleted_forms or not form.cleaned_data:
            continue
        material = form.instance
        material.competition = comp
        material.order = position
        material.save()
        position += 1


def _competition_initial(comp, *, with_dates: bool = True, with_results: bool = True) -> dict:
    """The submit form's fields, filled from an existing competition.

    Shared by editing (which wants everything) and cloning (which wants the shape of the event
    without the parts that belong to the edition being copied).
    """
    initial = {
        "title_ru": comp.title_ru or "",
        "title_kk": comp.title_kk or "",
        "title_en": comp.title_en or "",
        "description_ru": comp.description_ru or "",
        "description_kk": comp.description_kk or "",
        "description_en": comp.description_en or "",
        # Copied by a clone too: a weekly ride keeps its meeting point from one week to the next.
        "preview_text_ru": comp.preview_text_ru or "",
        "preview_text_kk": comp.preview_text_kk or "",
        "preview_text_en": comp.preview_text_en or "",
        "event_types": list(comp.event_types.values_list("pk", flat=True)),
        "disciplines": list(comp.disciplines.values_list("pk", flat=True)),
        "location": comp.location_id,
        "url_announcement": comp.url_announcement,
        "url_registration": comp.url_registration,
        "url_route": comp.url_route,
        "url_regulations": comp.url_regulations,
        "invite_only": comp.invite_only,
    }
    if with_dates:
        initial["date_start"] = comp.date_start
        initial["date_end"] = comp.date_end
    if with_results:
        initial["url_results"] = comp.url_results
    return initial


def _registration_initial(comp) -> dict:
    """The registration settings of an existing competition, as form initial data."""
    return {
        "registration_enabled": comp.registration_enabled,
        "registration_mode": comp.registration_mode,
        "birth_date_mode": comp.birth_date_mode,
        "require_approval": comp.require_approval,
        "require_payment": comp.require_payment,
        "allow_multiple_registrations": comp.allow_multiple_registrations,
        # As the organizer typed it: the wall-clock at the event's place (issue #344).
        "registration_deadline": (
            timezone.localtime(comp.registration_deadline, comp.timezone).replace(tzinfo=None)
            if comp.registration_deadline
            else None
        ),
        "max_participants": comp.max_participants,
        "show_unapproved_in_list": comp.show_unapproved_in_list,
        "show_unpaid_in_list": comp.show_unpaid_in_list,
        "show_approval_status_col": comp.show_approval_status_col,
        "show_payment_status_col": comp.show_payment_status_col,
        "additional_info_mode": comp.additional_info_mode,
        "additional_info_label": comp.additional_info_label,
        "show_additional_info_in_list": comp.show_additional_info_in_list,
        "additional_info_required": comp.additional_info_required,
        "relay_enabled": comp.relay_enabled,
        "relay_max_members": comp.relay_max_members,
    }


def _category_rows(comp, birth_date_mode: str = "") -> list[dict]:
    """A competition's registration categories in the shape the category editor reads.

    Birth bounds are dates in the database and either a date or a bare year in the editor, which is
    what birth_date_mode decides. Pass one to redraw the form the way it was just submitted, when
    the organizer changed that setting and the page is being re-rendered with their error.
    """
    from registrations.models import RegistrationCategory

    by_date = (birth_date_mode or comp.birth_date_mode) == "date"

    def bound(value):
        if value is None:
            return None
        return value.isoformat() if by_date else str(value.year)

    return [
        {**row, "birth_from": bound(row["birth_from"]), "birth_to": bound(row["birth_to"])}
        for row in RegistrationCategory.objects.filter(competition=comp, is_deleted=False).values(
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
    ]


class SubmitCompetitionView(ParticipantRequiredMixin, View):
    template_name = "calendar_app/submit.html"

    def _discipline_context(self, user, form):
        return {
            **_discipline_picker_context(form),
            "locations_data": _get_locations_data(user),
        }

    def _clone_source(self, request):
        """The competition being copied, when the page was opened from a Clone button.

        Only somebody who may edit that event may copy it: its description, its categories and its
        registration settings are as much its content as its title.
        """
        pk = request.GET.get("clone")
        if not pk or not pk.isdigit():
            return None
        comp = get_object_or_404(Competition, pk=int(pk), is_deleted=False)
        if not can_manage_or_own(request.user, comp):
            raise PermissionDenied
        return comp

    def _error_context(self, request, form, reg_form, is_organizer: bool) -> dict:
        """The page as the organizer left it, when their submission did not go through.

        The categories go back as they were posted: they live in a hidden field the JavaScript
        editor owns, so a re-render that forgets them silently empties the list -- which is a whole
        set of categories to retype after cloning an event that had eight of them.
        """
        return {
            "form": form,
            "reg_form": reg_form,
            "is_organizer_plus": is_organizer,
            "categories_json": request.POST.get("categories_json") or "[]",
            "initial_location_id": form["location"].value() or "",
            **self._discipline_context(request.user, form),
        }

    def get(self, request):
        import json

        source = self._clone_source(request)
        if source is None:
            form = SubmitCompetitionForm(user=request.user)
            reg_form = RegistrationSettingsForm()
            categories_json = "[]"
        else:
            # Everything but the parts that belong to the edition being copied: the dates are what
            # the organizer is here to change, and last year's results are not this year's.
            form = SubmitCompetitionForm(
                initial=_competition_initial(source, with_dates=False, with_results=False), user=request.user
            )
            reg_form = RegistrationSettingsForm(initial=_registration_initial(source))
            categories_json = json.dumps(_category_rows(source))
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "reg_form": reg_form,
                "is_organizer_plus": roles.at_least(request.user, roles.PUBLISH_EVENTS),
                "clone_source": source,
                "categories_json": categories_json,
                "initial_location_id": (source.location_id or "") if source else "",
                **self._discipline_context(request.user, form),
            },
        )

    def post(self, request):
        form = SubmitCompetitionForm(request.POST, request.FILES, user=request.user)
        reg_form = RegistrationSettingsForm(request.POST)
        is_organizer = roles.at_least(request.user, roles.PUBLISH_EVENTS)
        if form.is_valid() and (not is_organizer or reg_form.is_valid()):
            cd = form.cleaned_data
            if is_organizer and not _validate_deadline(form, reg_form, cd["date_start"], cd.get("date_end")):
                return render(request, self.template_name, self._error_context(request, form, reg_form, is_organizer))
            try:
                # Resolve, lock and re-validate the location, then save the competition in one
                # transaction so a concurrent delete/level-change of the venue can't bind this
                # competition to a removed node or a non-venue (review: competition-create vs delete).
                with transaction.atomic():
                    location = _resolve_competition_location(cd, request.user, approved=is_organizer)
                    location = lock_competition_location(
                        location, request.user, is_admin=roles.at_least(request.user, roles.APPROVE_PLACES)
                    )
                    comp = Competition(
                        title_ru=cd["title_ru"],
                        title_kk=cd.get("title_kk", ""),
                        title_en=cd.get("title_en", ""),
                        description_ru=cd.get("description_ru", ""),
                        description_kk=cd.get("description_kk", ""),
                        description_en=cd.get("description_en", ""),
                        preview_text_ru=cd.get("preview_text_ru", ""),
                        preview_text_kk=cd.get("preview_text_kk", ""),
                        preview_text_en=cd.get("preview_text_en", ""),
                        location=location,
                        date_start=cd["date_start"],
                        date_end=cd.get("date_end"),
                        url_announcement=cd.get("url_announcement", ""),
                        url_registration=cd.get("url_registration", ""),
                        url_route=cd.get("url_route", ""),
                        url_regulations=cd.get("url_regulations", ""),
                        url_results=cd.get("url_results", ""),
                        submitted_by=request.user,
                        invite_only=is_organizer and cd.get("invite_only", False),
                        is_top=cd.get("is_top", False),
                    )
                    uploads = ("file_announcement", "file_route", "file_regulations", "file_results", "preview_image")
                    for fname in uploads:
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
                    comp.event_types.set(cd.get("event_types") or [])
                    if is_organizer and reg_form.is_valid():
                        _save_categories(comp, reg_form, True)
                    # The event assistant's conversation that filled the form goes on from the
                    # event's edit page (issue #353).
                    link_conversation(request.POST.get("assistant_conversation"), comp, request.user)
            except LocationConflictError:
                form.add_error("location", _("This location is not available."))
            else:
                return redirect("calendar_list")
        return render(request, self.template_name, self._error_context(request, form, reg_form, is_organizer))


class EditCompetitionView(View):
    template_name = "calendar_app/edit.html"

    def _get_competition_or_403(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, comp):
            raise PermissionDenied
        return comp

    def get(self, request, pk):
        comp = self._get_competition_or_403(request, pk)
        # The top mark is the edition's, set by an admin: editing shows it, a clone starts without it.
        form = SubmitCompetitionForm(initial={**_competition_initial(comp), "is_top": comp.is_top}, user=request.user)
        reg_form = RegistrationSettingsForm(initial=_registration_initial(comp))
        import json

        categories = _category_rows(comp)
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
                "material_formset": _material_formset(request, comp),
                "categories_json": json.dumps(categories),
                "mode_locked": comp.registration_mode_locked,
                "is_organizer_plus": roles.at_least(request.user, roles.PUBLISH_EVENTS),
                **disc_ctx,
            },
        )

    def post(self, request, pk):
        comp = self._get_competition_or_403(request, pk)
        form = SubmitCompetitionForm(request.POST, request.FILES, user=request.user)
        reg_form = RegistrationSettingsForm(request.POST)
        # The coverage links are editable by whoever may edit the event at all -- the same permission
        # that got past _get_competition_or_403 above, with no separate organizer check.
        material_formset = _material_formset(request, comp)
        if form.is_valid() and reg_form.is_valid() and _materials_are_valid(material_formset):
            cd = form.cleaned_data
            if not _validate_deadline(form, reg_form, cd["date_start"], cd.get("date_end")):
                import json as _json

                _cats = _category_rows(comp, reg_form.cleaned_data.get("birth_date_mode"))
                return render(
                    request,
                    self.template_name,
                    {
                        "competition": comp,
                        "form": form,
                        "reg_form": reg_form,
                        "material_formset": material_formset,
                        "categories_json": _json.dumps(_cats),
                        "mode_locked": comp.registration_mode_locked,
                        "is_organizer_plus": roles.at_least(request.user, roles.PUBLISH_EVENTS),
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
            comp.preview_text_ru = cd.get("preview_text_ru", "")
            comp.preview_text_kk = cd.get("preview_text_kk", "")
            comp.preview_text_en = cd.get("preview_text_en", "")
            comp.date_start = cd["date_start"]
            comp.date_end = cd.get("date_end")
            comp.url_announcement = cd.get("url_announcement", "")
            comp.url_registration = cd.get("url_registration", "")
            comp.url_route = cd.get("url_route", "")
            comp.url_regulations = cd.get("url_regulations", "")
            comp.url_results = cd.get("url_results", "")
            uploads = ("file_announcement", "file_route", "file_regulations", "file_results", "preview_image")
            for fname in uploads:
                f = cd.get(fname)
                if f:
                    setattr(comp, fname, f)
            # Registration config (enable, categories, ...) stays organizer-only even when the author
            # editing their own submission is a participant (#200) -- mirror the submit view.
            is_org = roles.at_least(request.user, roles.PUBLISH_EVENTS)
            if is_org:
                comp.invite_only = cd.get("invite_only", False)
            if "is_top" in form.fields:  # an admin's form only; an author's edit leaves the mark alone
                comp.is_top = cd.get("is_top", False)
            try:
                # Resolve, lock and re-validate the location, then save in one transaction so a
                # concurrent delete/level-change of the venue can't bind this competition to a
                # removed node or a non-venue (review: competition-update vs delete).
                with transaction.atomic():
                    location = _resolve_competition_location(cd, request.user, approved=is_org)
                    comp.location = lock_competition_location(
                        location, request.user, is_admin=roles.at_least(request.user, roles.APPROVE_PLACES)
                    )
                    # After the location: the deadline is read in the zone of the event's place.
                    _apply_registration_settings(comp, reg_form, is_org)
                    _unpublish_if_geography_is_pending(comp, request.user)
                    comp.save()
                    comp.disciplines.set(cd.get("disciplines") or [])
                    comp.event_types.set(cd.get("event_types") or [])
                    _save_materials(material_formset, comp)
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
                "material_formset": material_formset,
                "categories_json": json.dumps(categories, default=str),
                "mode_locked": comp.registration_mode_locked,
                "is_organizer_plus": roles.at_least(request.user, roles.PUBLISH_EVENTS),
                **disc_ctx,
            },
        )


class ModerationView(ModeratorRequiredMixin, TemplateView):
    template_name = "calendar_app/moderate.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competitions = list(
            Competition.objects.filter(status=Competition.Status.PENDING_APPROVAL, is_deleted=False)
            .select_related("submitted_by", "location")
            .prefetch_related("event_types")
            .prefetch_related("disciplines__category")
            .order_by("date_start")
        )
        # An event on geography still under review can only be approved by someone who may also bless
        # that geography (ADMIN+); an organizer would just hit LocationPendingError. Don't show them
        # what they cannot act on -- leave those to the admins, who also see the pending locations.
        if not roles.at_least(self.request.user, roles.APPROVE_PLACES):
            competitions = [
                comp
                for comp in competitions
                if (comp.location_id is None or chain_is_approved(comp.location.get_parent())) and not comp.invite_only
            ]
        context["competitions"] = competitions
        context["reject_form"] = RejectCompetitionForm()
        if roles.at_least(self.request.user, roles.APPROVE_PLACES):
            context["pending_locations"] = (
                Location.objects.filter(proposal__status=LocationProposal.Status.PENDING_APPROVAL, is_deleted=False)
                .select_related("proposal__submitted_by")
                .order_by("path")
            )
            # Reported events (issue #233): already-public events a user flagged. They have no
            # "approve" step -- an admin edits, deletes, comments, or dismisses the report. Only
            # admins+ handle these, mirroring the proposed-locations queue above.
            context["reported_competitions"] = (
                Competition.objects.filter(
                    status=Competition.Status.APPROVED, is_deleted=False, reports__resolved=False
                )
                .distinct()
                .select_related("location")
                .prefetch_related("event_types")
                .prefetch_related(
                    "disciplines__category",
                    Prefetch(
                        "reports",
                        queryset=CompetitionReport.objects.filter(resolved=False).select_related("reported_by"),
                        to_attr="open_reports",
                    ),
                )
                .order_by("date_start")
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


class ApproveCompetitionView(ModeratorRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import LocationPendingError

        comp = get_object_or_404(Competition, pk=pk, status=Competition.Status.PENDING_APPROVAL, is_deleted=False)
        if not can_review(request.user, comp):
            raise Http404
        try:
            comp.approve(reviewer=request.user)
        except LocationPendingError:
            messages.error(
                request,
                _("This event's location is still awaiting review; an administrator must approve it first."),
            )
        except ValueError:
            pass  # another moderator reviewed it meanwhile, as the reject view allows
        return redirect(_safe_next(request, "calendar_moderate"))


class RejectCompetitionView(ModeratorRequiredMixin, View):
    def post(self, request, pk):
        comp = get_object_or_404(Competition, pk=pk, status=Competition.Status.PENDING_APPROVAL, is_deleted=False)
        if not can_review(request.user, comp):
            raise Http404
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
        competition = get_object_or_404(
            Competition, pk=competition_pk, status=Competition.Status.APPROVED, is_deleted=False
        )
        if not can_see(request.user, competition):
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


class ReportCompetitionView(ParticipantRequiredMixin, View):
    """A confirmed user flags a public event as inaccurate (issue #233).

    The event stays visible to everyone; the report surfaces it in the moderation queue for admins to
    edit, delete, comment, or dismiss. One open report per user -- a duplicate is answered with a
    friendly message rather than a second row (the DB constraint is the backstop for a race).
    """

    def post(self, request, pk):
        competition = get_object_or_404(public_events(), pk=pk)
        form = ReportCompetitionForm(request.POST)
        if not form.is_valid():
            first_errors = next(iter(form.errors.values()), [])
            messages.error(request, first_errors[0] if first_errors else _("Invalid submission."))
            return redirect("competition_detail", pk=pk)
        already = CompetitionReport.objects.filter(
            competition=competition, reported_by=request.user, resolved=False
        ).exists()
        if not already:
            try:
                # atomic() so a lost race (the partial-unique constraint firing) is a contained
                # savepoint rollback, not a broken request transaction / 500.
                with transaction.atomic():
                    CompetitionReport.objects.create(
                        competition=competition,
                        reported_by=request.user,
                        reason=form.cleaned_data["reason"],
                    )
            except IntegrityError:
                already = True  # a concurrent request already filed this user's open report
        if already:
            messages.info(request, _("You have already reported this event; a moderator will review it."))
        else:
            messages.success(request, _("Thank you. Your report has been sent to the moderators."))
        return redirect("competition_detail", pk=pk)


class DismissReportsView(ModeratorRequiredMixin, View):
    """Dismiss ("mark as fine") every open report on an event -- admins+ only (issue #233).

    Clears the event from the moderation queue. Editing or deleting the event stay separate manual
    actions available on the event's own page; dismissing just says "nothing to fix here".
    """

    def post(self, request, pk):
        if not roles.at_least(request.user, roles.MANAGE_ALL_EVENTS):
            raise PermissionDenied
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        updated = competition.reports.filter(resolved=False).update(
            resolved=True, resolved_at=timezone.now(), resolved_by=request.user
        )
        if updated:
            messages.success(request, _("Report dismissed; the event was cleared from the moderation queue."))
        return redirect(_safe_next(request, "calendar_moderate"))


class ToggleFavoriteView(LoginRequiredMixin, View):
    """Toggle the signed-in user's favorite mark on a competition (issue #183).

    Progressive enhancement: the star on the detail page posts here. A fetch() request (sending the
    ``X-Requested-With`` header) gets JSON ``{"favorited": bool}`` back so the star can update in
    place; a plain form submit (no JS) toggles and redirects to the detail page.
    """

    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, status=Competition.Status.APPROVED, is_deleted=False)
        if not can_see(request.user, competition):
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
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, competition):
            raise PermissionDenied
        competition.is_deleted = True
        competition.save(update_fields=["is_deleted"])
        return redirect("calendar_list")


class ResubmitCompetitionView(LoginRequiredMixin, View):
    """The author sends a rejected competition back for a fresh review (#200)."""

    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, competition):
            raise PermissionDenied
        try:
            competition.resubmit()
        except ValueError:
            messages.error(request, _("Only a rejected event can be resubmitted."))
        else:
            messages.success(request, _("Your event was sent for review again."))
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


class AcceptInviteView(View):
    """The invitation link of an invite-only event (issue #313).

    Accepting it takes signing in, because the invitation is kept against the account, which is what
    makes the event show up for that person everywhere afterwards. The link then sends them on to the
    event's own address, so the key does not linger in the address bar to be copied, shown or
    forwarded.

    Before that, a visitor who is not signed in -- a person, or a messenger fetching a preview of the
    pasted link -- is shown the event's name, line and picture and asked to sign in, so a chat shows
    the event rather than the login form (issue #351). Only for an event its invitees can open, the
    one "Share" hands this link out for: anyone holding the key sees it once signed in anyway.
    """

    def get(self, request, pk, key):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if competition.invite_only and competition.invite_key != key:
            # A stale or mistyped link says nothing about whether the event exists.
            raise Http404
        if not request.user.is_authenticated:
            if not competition.invite_only:
                return redirect("competition_detail", pk=pk)
            if competition.status != Competition.Status.APPROVED or competition.is_hidden:
                return redirect_to_login(request.get_full_path())
            context = {
                "competition": competition,
                "login_url": sign_in_url(request),
                **_link_preview_tags(request, competition),
            }
            response = render(request, "calendar_app/invite_preview.html", context)
            response["X-Robots-Tag"] = "noindex"
            return response
        if competition.invite_only:
            CompetitionInvite.objects.get_or_create(competition=competition, user=request.user)
        return redirect("competition_detail", pk=pk)


class RegenerateInviteKeyView(LoginRequiredMixin, View):
    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False, invite_only=True)
        if not manages(request.user, competition):
            raise PermissionDenied
        competition.regenerate_invite_key()
        messages.success(
            request, _("Invitation link replaced. The old link no longer works; people already invited keep access.")
        )
        return redirect("competition_detail", pk=pk)


class RegenerateUploadTokenView(LoginRequiredMixin, View):
    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, competition):
            raise PermissionDenied
        competition.upload_token = uuid.uuid4()
        competition.save(update_fields=["upload_token"])
        messages.success(request, _("Timing token regenerated. The previous token no longer works."))
        return redirect("competition_detail", pk=pk)


class DeleteUploadTokenView(LoginRequiredMixin, View):
    def post(self, request, pk):
        competition = get_object_or_404(Competition, pk=pk, is_deleted=False)
        if not can_manage_or_own(request.user, competition):
            raise PermissionDenied
        competition.upload_token = None
        competition.save(update_fields=["upload_token"])
        messages.success(request, _("Timing token deleted. Timing tools can no longer access this event."))
        return redirect("competition_detail", pk=pk)
