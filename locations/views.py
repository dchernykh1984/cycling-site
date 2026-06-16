from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from accounts.models import User

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
_ORGANIZER_RANK = User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)


def _can_manage_locations(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


def _can_add_location_directly(user) -> bool:
    """Organizer+ may add approved locations directly; everyone else proposes (issue #111)."""
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ORGANIZER_RANK)


def _get_all_locations_json() -> list:
    """Depths 1-3 for the cascade widget on the location form."""
    from locations.models import Location

    return list(
        Location.objects.filter(is_deleted=False, depth__in=[1, 2, 3])
        .order_by("path")
        .values("pk", "depth", "path", "name_ru", "name_kk", "name_en", "is_hidden")
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
    # Any registered user may propose a location; organizer+ add it approved directly.
    def get(self, request):
        from locations.forms import LocationForm

        form = LocationForm(location_depth=4)
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": False,
                "can_manage": _can_manage_locations(request.user),
                "map_url": _get_map_url(),
                "all_locations_json": _get_all_locations_json(),
                "venues_json": _get_venues_json(),
                "location_depth": 4,
            },
        )

    def post(self, request):
        from locations.forms import LocationForm
        from locations.models import LocationProposal

        form = LocationForm(request.POST, location_depth=4)
        if form.is_valid():
            cd = form.cleaned_data
            name = cd["name_ru"] or cd.get("name_kk") or cd.get("name_en") or ""
            city = cd["city"]
            approved = _can_add_location_directly(request.user)
            venue = city.add_child(
                name=name,
                name_ru=cd["name_ru"],
                name_kk=cd.get("name_kk") or "",
                name_en=cd.get("name_en") or "",
                lat=cd.get("lat"),
                lng=cd.get("lng"),
                # Only managers may create hidden fallback venues.
                is_hidden=cd.get("is_hidden", False) if _can_manage_locations(request.user) else False,
            )
            # Non-managers propose; a pending proposal hides the venue from others until approved.
            if not approved:
                LocationProposal.objects.create(location=venue, submitted_by=request.user)
            messages.success(request, _("Location added.") if approved else _("Location proposed for review."))
            return redirect(_get_map_url())
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": False,
                "can_manage": _can_manage_locations(request.user),
                "map_url": _get_map_url(),
                "all_locations_json": _get_all_locations_json(),
                "venues_json": _get_venues_json(),
                "location_depth": 4,
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
        location_depth = location.depth

        initial_city = location.get_parent() if location_depth >= 4 else None

        form = LocationForm(
            initial={
                "name_ru": location.name_ru,
                "name_kk": location.name_kk,
                "name_en": location.name_en,
                "city": initial_city,
                "lat": location.lat,
                "lng": location.lng,
                "is_hidden": location.is_hidden,
            },
            exclude_pk=pk,
            location_depth=location_depth,
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
                "all_locations_json": _get_all_locations_json(),
                "venues_json": _get_venues_json(),
                "location_depth": location_depth,
            },
        )

    def post(self, request, pk):
        from locations.forms import LocationForm
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        location_depth = location.depth
        form = LocationForm(request.POST, exclude_pk=pk, location_depth=location_depth)
        if form.is_valid():
            cd = form.cleaned_data
            location.name_ru = cd["name_ru"]
            location.name_kk = cd.get("name_kk") or ""
            location.name_en = cd.get("name_en") or ""
            location.name = location.name_ru or location.name_kk or location.name_en
            location.lat = cd.get("lat")
            location.lng = cd.get("lng")
            location.is_hidden = cd.get("is_hidden", False)
            location.save(update_fields=["name", "name_ru", "name_kk", "name_en", "lat", "lng", "is_hidden"])

            new_city = cd.get("city")
            if new_city is not None:
                current_parent = location.get_parent()
                if current_parent is None or current_parent.pk != new_city.pk:
                    location.refresh_from_db()
                    new_city.refresh_from_db()
                    _safe_move(location, new_city, pos="sorted-child")

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
                "all_locations_json": _get_all_locations_json(),
                "venues_json": _get_venues_json(),
                "location_depth": location_depth,
            },
        )
