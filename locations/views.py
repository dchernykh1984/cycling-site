from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from accounts.models import User

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)


def _can_manage_locations(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.get_role_rank() >= _ADMIN_RANK)


def _parent_choices(form) -> list:
    field = form.fields["parent"]
    choices = [("", "")]
    for loc in field.queryset:
        choices.append((loc.pk, field.label_from_instance(loc)))
    return choices


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
    def get(self, request):
        from locations.forms import LocationForm

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        form = LocationForm()
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": False,
                "map_url": _get_map_url(),
                "parent_choices": _parent_choices(form),
            },
        )

    def post(self, request):
        from locations.forms import LocationForm
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        form = LocationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            name = cd["name_ru"] or cd.get("name_kk") or cd.get("name_en") or ""
            kwargs = dict(
                name=name,
                name_ru=cd["name_ru"],
                name_kk=cd.get("name_kk") or "",
                name_en=cd.get("name_en") or "",
                lat=cd.get("lat"),
                lng=cd.get("lng"),
                is_hidden=cd.get("is_hidden", False),
            )
            parent = cd.get("parent")
            if parent:
                parent.add_child(**kwargs)
            else:
                Location.add_root(**kwargs)
            messages.success(request, _("Location added."))
            return redirect(_get_map_url())
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": False,
                "map_url": _get_map_url(),
                "parent_choices": _parent_choices(form),
            },
        )


class LocationEditView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from locations.forms import LocationForm
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        current_parent = location.get_parent()
        form = LocationForm(
            initial={
                "name_ru": location.name_ru,
                "name_kk": location.name_kk,
                "name_en": location.name_en,
                "parent": current_parent,
                "lat": location.lat,
                "lng": location.lng,
                "is_hidden": location.is_hidden,
            },
            exclude_pk=pk,
        )
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": True,
                "location": location,
                "map_url": _get_map_url(),
                "parent_choices": _parent_choices(form),
            },
        )

    def post(self, request, pk):
        from locations.forms import LocationForm
        from locations.models import Location

        if not _can_manage_locations(request.user):
            raise PermissionDenied
        location = get_object_or_404(Location, pk=pk, is_deleted=False)
        form = LocationForm(request.POST, exclude_pk=pk)
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

            new_parent = cd.get("parent")
            current_parent = location.get_parent()
            current_parent_pk = current_parent.pk if current_parent else None
            new_parent_pk = new_parent.pk if new_parent else None
            if current_parent_pk != new_parent_pk:
                location.refresh_from_db()
                if new_parent:
                    new_parent.refresh_from_db()
                    _safe_move(location, new_parent, pos="sorted-child")
                else:
                    root = Location.get_root_nodes().exclude(pk=pk).first()
                    if root:
                        _safe_move(location, root, pos="sorted-sibling")

            messages.success(request, _("Location saved."))
            return redirect(_get_map_url())
        return render(
            request,
            "locations/location_form.html",
            {
                "form": form,
                "is_edit": True,
                "location": location,
                "map_url": _get_map_url(),
                "parent_choices": _parent_choices(form),
            },
        )
