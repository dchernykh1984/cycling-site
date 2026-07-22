from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from accounts.access import ParticipantRequiredMixin
from accounts.models import User

_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)
_PARTICIPANT_RANK = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)


def _can_manage_locations(user) -> bool:
    from locations.models import can_manage_locations

    return can_manage_locations(user)


def _can_add_location_directly(user) -> bool:
    """Organizer+ may add approved locations directly; everyone else proposes (issue #111)."""
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ORGANIZER_RANK)


def _get_all_locations_json(user=None) -> list:
    """Depths 1-3 for the cascade widget on the location form: public nodes plus the user's own
    pending proposals (a foreign pending node must not appear as a selectable parent)."""
    from locations.models import selectable_parent_locations

    return list(
        selectable_parent_locations(user).values("pk", "depth", "path", "name_ru", "name_kk", "name_en", "is_hidden")
    )


def _get_venues_json() -> list:
    """Selectable venues (depth-4, not hidden, with coordinates) shown as reference markers
    on the location form map so users can see existing venues and avoid duplicates (#118)."""
    from django.db.models import Q

    from locations.models import Location, LocationProposal

    visible = Q(proposal__isnull=True) | Q(proposal__status=LocationProposal.Status.APPROVED)
    rows = (
        Location.objects.filter(is_deleted=False, is_hidden=False, depth=4, lat__isnull=False, lng__isnull=False)
        .filter(visible)
        .values("pk", "name_ru", "name_kk", "name_en", "lat", "lng")
    )
    return [{**r, "lat": float(r["lat"]), "lng": float(r["lng"])} for r in rows]


def _get_map_url() -> str:
    from locations.models import LocationsMapPage

    page = LocationsMapPage.objects.live().first()
    return page.url if page else "/"


def _safe_return_url(request, default: str) -> str:
    """A same-origin return target (path + query) from ``next`` or the referer, so an action
    taken on ``?page=N&location=...`` returns to that page/filter instead of the first page.

    The candidate is validated with Django's host/scheme check (which also rejects scheme-relative
    ``//evil`` and ``\\evil`` open-redirect forms), then reduced to path + query so we never emit a
    foreign host."""
    candidate = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER", "")
    if not candidate or not url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return default
    parsed = urlparse(candidate)
    if not parsed.path:
        return default
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


class LocationDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location, LocationConflictError, soft_delete_location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        # Soft-deleting a node with a live subtree/competitions would orphan them under a vanished
        # ancestor. soft_delete_location re-checks this under a row lock, so a concurrent create
        # can't slip a child in between the check and the delete.
        try:
            soft_delete_location(location)
        except LocationConflictError:
            messages.error(request, _("Cannot delete a location that still has nested locations or competitions."))
        return redirect(_safe_return_url(request, "/"))


class LocationHideView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        if location.is_system_fallback:
            messages.error(request, _("System fallback locations must remain hidden."))
        else:
            location.is_hidden = not location.is_hidden
            location.save(update_fields=["is_hidden"])
        return redirect(_safe_return_url(request, "/"))


class LocationCreateView(ParticipantRequiredMixin, View):
    # Confirmed users (PARTICIPANT+) may propose a location; organizer+ add it approved
    # directly. Guests (unconfirmed email) must verify first, like submitting a competition.
    def get(self, request):
        from locations.forms import LocationForm

        form = LocationForm(user=request.user, can_manage=_can_manage_locations(request.user))
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": False,
                "can_manage": _can_manage_locations(request.user),
                "map_url": _get_map_url(),
                "all_locations_json": _get_all_locations_json(request.user),
                "venues_json": _get_venues_json(),
            },
        )

    def post(self, request):
        from locations.forms import LocationForm
        from locations.models import LocationConflictError, LocationProposal, add_location_child

        form = LocationForm(request.POST, user=request.user, can_manage=_can_manage_locations(request.user))
        if form.is_valid():
            cd = form.cleaned_data
            name = cd["name_ru"] or cd.get("name_kk") or cd.get("name_en") or ""
            # The deepest selected cascade node is the parent; None means a new country.
            # The new location's level is always parent.depth + 1 (depth 1 for a country).
            parent = cd.get("parent")
            new_depth = parent.depth + 1 if parent is not None else 1
            can_direct = _can_add_location_directly(request.user)
            # Structural nodes (country/region/city) are admin-only, matching the API and the role
            # contract; organizer+ may only add a depth-4 venue under a city, and everyone else
            # proposes such a venue. The proposal/approve/reject workflow stays venue-only.
            if new_depth != 4 and not _can_manage_locations(request.user):
                raise PermissionDenied
            try:
                # add_location_child locks the parent and the proposal shares the transaction, so a
                # concurrent delete of the parent can't leave the new node orphaned.
                with transaction.atomic():
                    new_location = add_location_child(
                        parent,
                        name=name,
                        name_ru=cd["name_ru"],
                        name_kk=cd.get("name_kk") or "",
                        name_en=cd.get("name_en") or "",
                        lat=cd.get("lat"),
                        lng=cd.get("lng"),
                        # Only managers may create hidden fallback venues.
                        is_hidden=cd.get("is_hidden", False) if _can_manage_locations(request.user) else False,
                    )
                    # A proposal only ever attaches to a venue a non-privileged user proposed; it
                    # hides the venue from others until approved.
                    if not can_direct:
                        LocationProposal.objects.create(location=new_location, submitted_by=request.user)
            except LocationConflictError:
                form.add_error("parent", _("The selected parent location is no longer available."))
            else:
                messages.success(request, _("Location added.") if can_direct else _("Location proposed for review."))
                return redirect(_get_map_url())
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": False,
                "can_manage": _can_manage_locations(request.user),
                "map_url": _get_map_url(),
                "all_locations_json": _get_all_locations_json(request.user),
                "venues_json": _get_venues_json(),
            },
        )


class LocationApproveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location, LocationProposal

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        # Only act on a pending proposal; approving a non-pending location is a 404.
        location = get_object_or_404(
            Location, pk=pk, is_deleted=False, proposal__status=LocationProposal.Status.PENDING_APPROVAL
        )
        location.approve_with_competition(request.user)
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)


class LocationRejectView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location, LocationConflictError, LocationProposal

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        # Only reject a pending proposal; rejecting a non-pending location (which would
        # destructively reset its competitions) is a 404.
        location = get_object_or_404(
            Location, pk=pk, is_deleted=False, proposal__status=LocationProposal.Status.PENDING_APPROVAL
        )
        try:
            location.reject_and_reset_competitions()
        except LocationConflictError:
            messages.error(request, _("This location proposal is no longer pending."))
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)


class LocationEditView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from locations.forms import LocationForm
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)

        form = LocationForm(
            initial={
                "name_ru": location.name_ru,
                "name_kk": location.name_kk,
                "name_en": location.name_en,
                # Pre-fill the cascade with the current parent chain; its depth determines
                # which selects are filled (a country's parent is None -> all "--").
                "parent": location.get_parent(),
                "lat": location.lat,
                "lng": location.lng,
                "is_hidden": location.is_hidden,
            },
            exclude_pk=pk,
            user=request.user,
            can_manage=_can_manage_locations(request.user),
        )
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": True,
                "can_manage": _can_manage_locations(request.user),
                "location": location,
                "is_fallback": location.is_system_fallback,
                "map_url": _get_map_url(),
                "next_url": _safe_return_url(request, _get_map_url()),
                "all_locations_json": _get_all_locations_json(request.user),
                "venues_json": _get_venues_json(),
            },
        )

    def post(self, request, pk):
        from locations.forms import LocationForm
        from locations.models import Location, LocationConflictError, move_location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        form = LocationForm(
            request.POST,
            exclude_pk=pk,
            instance=location,
            user=request.user,
            can_manage=_can_manage_locations(request.user),
        )
        if form.is_valid():
            cd = form.cleaned_data
            new_parent = cd.get("parent")
            try:
                # The field save and the re-parent move must be one transaction (a failed move must
                # not leave a half-applied edit). move_location locks the row and re-checks the level
                # change under that lock, so a child appearing between validation and the move is caught.
                with transaction.atomic():
                    # Assign + save under the default language so modeltranslation keeps the canonical
                    # ``name`` synced to ``name_ru`` (its descriptor mirrors the *active* language on
                    # save). Editing under a kk/en locale would otherwise store that translation as the
                    # canonical name; the per-language columns are written explicitly and stay correct.
                    with translation.override(settings.MODELTRANSLATION_DEFAULT_LANGUAGE):
                        location.name_ru = cd["name_ru"]
                        location.name_kk = cd.get("name_kk") or ""
                        location.name_en = cd.get("name_en") or ""
                        location.name = location.name_ru or location.name_kk or location.name_en
                        location.lat = cd.get("lat")
                        location.lng = cd.get("lng")
                        location.is_hidden = cd.get("is_hidden", False)
                        location.save(
                            update_fields=["name", "name_ru", "name_kk", "name_en", "lat", "lng", "is_hidden"]
                        )
                    move_location(location, new_parent)
            except LocationConflictError:
                form.add_error(
                    "parent",
                    _("This location has nested locations or competitions, so its level cannot be changed."),
                )
            else:
                messages.success(request, _("Location saved."))
                return redirect(_safe_return_url(request, _get_map_url()))
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": True,
                "can_manage": _can_manage_locations(request.user),
                "location": location,
                "is_fallback": location.is_system_fallback,
                "map_url": _get_map_url(),
                "next_url": _safe_return_url(request, _get_map_url()),
                "all_locations_json": _get_all_locations_json(request.user),
                "venues_json": _get_venues_json(),
            },
        )
