from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from accounts.models import User

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)
_PARTICIPANT_RANK = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)


def _can_manage_locations(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


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


def _safe_move(location, target, pos: str) -> None:
    # modeltranslation's _rewrite_f() mutates Length() expression objects,
    # which became read-only properties in Django 4+, crashing treebeard's
    # bulk path update during move().  We temporarily make it a no-op for
    # expression types it cannot rewrite.
    import unittest.mock

    from modeltranslation.manager import MultilingualQuerySet

    orig = MultilingualQuerySet._rewrite_f

    def _patched(self, q):  # type: ignore[misc]
        try:
            return orig(self, q)
        except AttributeError:
            return q

    with unittest.mock.patch.object(MultilingualQuerySet, "_rewrite_f", _patched):
        location.move(target, pos=pos)


def _get_map_url() -> str:
    from locations.models import LocationsMapPage

    page = LocationsMapPage.objects.live().first()
    return page.url if page else "/"


class LocationDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        location.is_deleted = True
        location.save(update_fields=["is_deleted"])
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)


class LocationHideView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        location.is_hidden = not location.is_hidden
        location.save(update_fields=["is_hidden"])
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)


class LocationCreateView(LoginRequiredMixin, View):
    # Confirmed users (PARTICIPANT+) may propose a location; organizer+ add it approved
    # directly. Guests (unconfirmed email) must verify first, like submitting a competition.
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_superuser and request.user.get_role_rank() < _PARTICIPANT_RANK:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from locations.forms import LocationForm

        form = LocationForm(user=request.user)
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
        from locations.models import LocationProposal, add_location_child

        form = LocationForm(request.POST, user=request.user)
        if form.is_valid():
            cd = form.cleaned_data
            name = cd["name_ru"] or cd.get("name_kk") or cd.get("name_en") or ""
            # The deepest selected cascade node is the parent; None means a new country.
            # The new location's level is always parent.depth + 1 (depth 1 for a country).
            parent = cd.get("parent")
            new_depth = parent.depth + 1 if parent is not None else 1
            can_direct = _can_add_location_directly(request.user)
            # The proposal/approve/reject workflow is venue-only. Structural nodes (country/
            # region/city) are never proposed: only organizer+ may create them, always approved.
            # Everyone else is limited to proposing a depth-4 venue under an existing city.
            if new_depth != 4 and not can_direct:
                raise PermissionDenied
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
            # A proposal only ever attaches to a venue a non-privileged user proposed; it hides
            # the venue from others until approved.
            if not can_direct:
                LocationProposal.objects.create(location=new_location, submitted_by=request.user)
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
        location.approve_with_competition()
        safe_path = urlparse(request.META.get("HTTP_REFERER", "")).path or "/"
        return redirect(safe_path)


class LocationRejectView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from locations.models import Location, LocationProposal

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        # Only reject a pending proposal; rejecting a non-pending location (which would
        # destructively reset its competitions) is a 404.
        location = get_object_or_404(
            Location, pk=pk, is_deleted=False, proposal__status=LocationProposal.Status.PENDING_APPROVAL
        )
        location.reject_and_reset_competitions()
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
        )
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": True,
                "can_manage": _can_manage_locations(request.user),
                "location": location,
                "map_url": _get_map_url(),
                "all_locations_json": _get_all_locations_json(request.user),
                "venues_json": _get_venues_json(),
            },
        )

    def post(self, request, pk):
        from locations.forms import LocationForm
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        form = LocationForm(request.POST, exclude_pk=pk, instance=location, user=request.user)
        if form.is_valid():
            cd = form.cleaned_data
            new_parent = cd.get("parent")
            # The field save and the re-parent move must be one transaction: a failed move must
            # not leave a half-applied edit (renamed but not moved, or vice versa).
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
                    location.save(update_fields=["name", "name_ru", "name_kk", "name_en", "lat", "lng", "is_hidden"])

                # Re-parent (and re-level) when the chosen parent differs from the current one. A
                # None parent re-roots the node as a country; otherwise it becomes parent.depth + 1.
                # The form forbids a level change while the node still has children/competitions.
                current_parent = location.get_parent()
                current_pk = current_parent.pk if current_parent is not None else None
                new_pk = new_parent.pk if new_parent is not None else None
                if new_pk != current_pk:
                    location.refresh_from_db()
                    if new_parent is None:
                        # Become a root by joining an existing root as a sorted sibling.
                        root = (
                            Location.objects.filter(is_deleted=False, depth=1)
                            .exclude(pk=location.pk)
                            .order_by("path")
                            .first()
                        )
                        if root is not None:
                            _safe_move(location, root, pos="sorted-sibling")
                    else:
                        new_parent.refresh_from_db()
                        _safe_move(location, new_parent, pos="sorted-child")

            messages.success(request, _("Location saved."))
            return redirect(_get_map_url())
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": True,
                "can_manage": _can_manage_locations(request.user),
                "location": location,
                "map_url": _get_map_url(),
                "all_locations_json": _get_all_locations_json(request.user),
                "venues_json": _get_venues_json(),
            },
        )
