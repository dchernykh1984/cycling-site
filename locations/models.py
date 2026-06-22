import threading
from typing import ClassVar

from django.conf import settings
from django.core.paginator import Paginator
from django.db import connection, models, transaction
from django.utils import translation
from django.utils.translation import gettext
from treebeard.mp_tree import MP_Node
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page
from wagtail.search import index
from wagtail_localize.fields import SynchronizedField

from cycling_site.page_mixins import AsciiSlugMixin


class LocationConflictError(Exception):
    """A concurrent mutation made the requested location change unsafe (e.g. the parent was
    soft-deleted, or a child/competition appeared) -- callers turn this into a user-facing error."""


# Arbitrary fixed key for the transaction-scoped advisory lock that serializes every structural
# mutation of the materialized-path tree. Row locks still protect competition/location contracts;
# this namespace lock additionally prevents a subtree bulk move from racing a descendant insert.
_TREE_MUTATION_LOCK = 0x10C_A710

# modeltranslation's compatibility patch below changes a process-global class method. Keep the
# context strictly single-threaded even when independent DB trees are moved by concurrent requests.
_MODELTRANSLATION_PATCH_LOCK = threading.RLock()


def _lock_tree_mutation_namespace():
    """Serialize structural tree writes with a transaction-scoped advisory lock on PostgreSQL.

    Other supported development/test backends serialize writes at the database level, so this is a
    no-op there. Call this before acquiring location row locks to keep lock ordering consistent.
    """
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_TREE_MUTATION_LOCK])


def add_location_child(parent, **kwargs):
    """Append a child under ``parent`` at the next free path, sidestepping treebeard's
    sorted ``add_child``.  When ``parent`` is ``None`` the node is appended as a new root
    (depth-1 country), sidestepping the sorted ``add_root`` for the same reason.

    A sorted MP tree assumes a sibling's path order matches its sort order, so inserting
    shifts later siblings' paths. Renaming a location changes its ``name`` sort key without
    re-pathing, which breaks that invariant and makes the next sorted insert collide on the
    unique ``path`` constraint -- a 500 when proposing/creating a venue. Appending at the
    real last path never shifts an existing node, and recomputing ``numchild`` heals a
    counter that has drifted (e.g. ``is_leaf`` wrongly reporting a populated node as empty).

    The whole insert runs in a transaction that takes the tree mutation lock and locks the parent
    row (``select_for_update``). This serializes inserts with delete/move operations, including a
    same-depth move of an ancestor whose treebeard bulk UPDATE also changes this parent's path.
    """
    cls = parent.__class__ if parent is not None else Location
    with transaction.atomic():
        _lock_tree_mutation_namespace()
        if parent is not None:
            # Re-read the parent under a row lock; refuse if a concurrent delete removed it.
            locked = cls.objects.select_for_update().get(pk=parent.pk)
            if locked.is_deleted:
                raise LocationConflictError("Parent location was removed")
            # The tree is four levels (country/region/city/venue); never nest under a venue. Also
            # closes a race where the parent was concurrently moved down to depth 4 before we lock.
            if locked.depth >= 4:
                raise LocationConflictError("Parent location is already at the deepest level")
            depth = locked.depth + 1
            siblings = list(
                cls.objects.filter(
                    depth=depth,
                    path__range=cls._get_children_path_interval(locked.path),
                ).order_by("path")
            )
        else:
            depth = 1
            siblings = list(cls.objects.filter(depth=1).order_by("path"))
        last = siblings[-1] if siblings else None
        if last is not None:
            newpath = last._inc_path()
        elif parent is not None:
            newpath = cls._get_path(locked.path, depth, 1)
        else:
            newpath = cls._get_path(None, 1, 1)
        obj = cls(path=newpath, depth=depth, numchild=0, **kwargs)
        obj.save()
        if parent is not None:
            new_count = len(siblings) + 1
            if locked.numchild != new_count:
                cls.objects.filter(pk=parent.pk).update(numchild=new_count)
            # Keep the caller's instance fresh: some callers immediately use parent.get_children(),
            # which short-circuits on a stale numchild.
            parent.numchild = new_count
        return obj


class Location(MP_Node, index.Indexed):
    name = models.CharField(max_length=255)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    is_hidden = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    node_order_by: ClassVar[list] = ["sort_order", "name"]

    # name_ru / name_kk / name_en are generated by modeltranslation
    search_fields: ClassVar[list] = [
        index.SearchField("name_ru"),
        index.SearchField("name_kk"),
        index.SearchField("name_en"),
        index.FilterField("is_deleted"),
        index.FilterField("is_hidden"),
    ]

    panels: ClassVar[list] = [
        FieldPanel("name"),
        FieldPanel("lat"),
        FieldPanel("lng"),
    ]

    def __str__(self) -> str:
        return self.name or f"Location #{self.pk}"

    @staticmethod
    def _localized_names(source: str) -> dict:
        """Return {ru, kk, en} translations of a gettext source string."""
        names = {}
        for lang in ("ru", "kk", "en"):
            with translation.override(lang):
                names[lang] = gettext(source)
        return names

    @property
    def is_pending(self) -> bool:
        """True while the location has an unresolved proposal (issue #111)."""
        proposal = getattr(self, "proposal", None)
        return proposal is not None and proposal.status == LocationProposal.Status.PENDING_APPROVAL

    @property
    def is_system_fallback(self) -> bool:
        try:
            mapping = self.fallback_identity
        except LocationFallback.DoesNotExist:
            return False
        return mapping is not None

    @classmethod
    def propose_venue(cls, city, name, lat=None, lng=None, *, submitted_by=None, approved=False) -> "Location":
        """Create a depth-4 venue under ``city``; pending (with a proposal) unless ``approved``."""
        venue = add_location_child(
            city, name=name, name_ru=name, name_kk=name, name_en=name, lat=lat, lng=lng, is_hidden=False
        )
        if not approved:
            LocationProposal.objects.create(location=venue, submitted_by=submitted_by)
        return venue

    @classmethod
    def get_or_create_other_location(cls, city) -> "Location":
        """Return the city's unique system fallback venue, creating it under a city row lock."""
        with transaction.atomic():
            _lock_tree_mutation_namespace()
            try:
                locked_city = cls.objects.select_for_update().get(pk=city.pk, is_deleted=False, depth=3)
            except cls.DoesNotExist:
                raise LocationConflictError("Fallback city is no longer available") from None

            mapping = (
                LocationFallback.objects.select_for_update().select_related("location").filter(city=locked_city).first()
            )
            if mapping is not None:
                existing = mapping.location
                if existing.is_deleted or not existing.is_hidden:
                    existing.is_deleted = False
                    existing.is_hidden = True
                    existing.save(update_fields=["is_deleted", "is_hidden"])
                return existing

            names = cls._localized_names("Other location")
            fallback = add_location_child(
                locked_city,
                name=names["ru"],
                name_ru=names["ru"],
                name_kk=names["kk"],
                name_en=names["en"],
                is_hidden=True,
            )
            LocationFallback.objects.create(city=locked_city, location=fallback)
            return fallback

    def approve_with_competition(self) -> None:
        """Auto-approve a pending location when its competition is approved."""
        proposal = getattr(self, "proposal", None)
        if proposal is not None and proposal.status != LocationProposal.Status.APPROVED:
            proposal.status = LocationProposal.Status.APPROVED
            proposal.save(update_fields=["status"])

    def reject_and_reset_competitions(self) -> None:
        """Atomically reject a pending venue, move its competitions to the city fallback and delete it."""
        with transaction.atomic():
            _lock_tree_mutation_namespace()
            parent = self.get_parent()
            if parent is None:
                raise LocationConflictError("Proposed venue no longer has a parent")

            rows = {
                row.pk: row
                for row in Location.objects.select_for_update().filter(pk__in={self.pk, parent.pk}).order_by("pk")
            }
            locked = rows.get(self.pk)
            locked_parent = rows.get(parent.pk)
            if locked is None or locked_parent is None or locked.is_deleted:
                raise LocationConflictError("Location proposal is no longer available")
            proposal = (
                LocationProposal.objects.select_for_update()
                .filter(location=locked, status=LocationProposal.Status.PENDING_APPROVAL)
                .first()
            )
            if proposal is None:
                raise LocationConflictError("Location proposal is no longer pending")

            fallback = self.get_or_create_other_location(locked_parent)
            locked.competitions.update(location=fallback)
            locked.is_deleted = True
            locked.save(update_fields=["is_deleted"])

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"


class LocationProposal(models.Model):
    """A user-proposed location awaiting moderation (issue #111).

    Locations seeded or created by organizer+ have no proposal and are public at once.
    A pending proposal makes the location visible only to its proposer until approved;
    approving the competition that uses it (or a moderator) approves the proposal.
    """

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"

    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="proposal")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Proposal #{self.pk} for location {self.location_id} ({self.status})"


class LocationFallback(models.Model):
    """Stable identity of the single system fallback venue belonging to a city."""

    city = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="fallback_mapping")
    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="fallback_identity")

    def __str__(self) -> str:
        return f"Fallback location {self.location_id} for city {self.city_id}"


def competition_location_block_reason(location, user, *, is_admin=False) -> str | None:
    """Why ``user`` may not attach a competition to ``location`` (review #3), else None.

    Shared by the web submit/edit form and the competition API so a forged request can't
    use a deleted location or another user's pending (unmoderated) proposal.
    """
    if location is None:
        return None
    if getattr(location, "is_deleted", False):
        return "Location is deleted"
    # A competition must point at a specific venue (depth 4), never a country/region/city.
    if location.depth != 4:
        return "Competition location must be a specific venue, not a country/region/city"
    proposal = getattr(location, "proposal", None)
    if proposal is not None and proposal.status == LocationProposal.Status.PENDING_APPROVAL and not is_admin:
        owner_id = proposal.submitted_by_id
        if not (getattr(user, "is_authenticated", False) and owner_id == getattr(user, "pk", None)):
            return "Location proposal belongs to another user"
    return None


def lock_competition_location(location, user, *, is_admin=False):
    """Lock ``location`` ``FOR UPDATE`` and re-validate it as a competition target under that lock,
    then return the locked row (``None`` if ``location`` is ``None``). A concurrent soft-delete or
    level change locks the same row, so binding a competition to the location serializes with them
    and can never attach it to a deleted node or one that is no longer a depth-4 venue. Must be
    called inside the same ``transaction.atomic()`` that saves the competition. Raises
    ``LocationConflictError`` if the location is no longer usable."""
    if location is None:
        return None
    try:
        locked = Location.objects.select_for_update().get(pk=location.pk)
    except Location.DoesNotExist:
        raise LocationConflictError("Location no longer exists") from None
    if competition_location_block_reason(locked, user, is_admin=is_admin):
        raise LocationConflictError("Location is no longer usable for a competition")
    return locked


def nearest_visible_ancestor_with_coords(loc, by_path, step):
    """The nearest ancestor of ``loc`` (city -> region -> country) that is NOT hidden and
    has coordinates, looked up in ``by_path`` (path -> Location). Hidden ancestors are
    skipped so a hidden node never becomes a marker; None if none qualifies. ``by_path``
    is expected to exclude deleted nodes, so deleted ancestors are skipped too."""
    path = loc.path[:-step]
    while path:
        anc = by_path.get(path)
        if anc is not None and not anc.is_hidden and anc.lat is not None and anc.lng is not None:
            return anc
        path = path[:-step]
    return None


def map_display_node(loc, by_path, step):
    """The node ``loc`` should be drawn as on a map: itself when it is a visible node with
    coordinates, otherwise the nearest non-hidden ancestor (city -> region -> country) that
    has coordinates. A hidden node (the "other location" placeholder) is never drawn and
    always resolves up to the real place, so the marker shows its name. None if nothing
    qualifies."""
    if not loc.is_hidden and loc.lat is not None and loc.lng is not None:
        return loc
    return nearest_visible_ancestor_with_coords(loc, by_path, step)


def _subtree_descendants(location, *, include_deleted):
    """Physical descendants of ``location`` (an MP descendant's path starts with the ancestor's
    path); ``include_deleted`` keeps soft-deleted nodes, which still occupy the tree physically."""
    qs = Location.objects.filter(path__startswith=location.path, depth__gt=location.depth)
    return qs if include_deleted else qs.filter(is_deleted=False)


def location_subtree_has_live_competitions(location) -> bool:
    """True if any non-deleted competition points at a non-deleted node in ``location``'s subtree.
    A soft-deleted competition no longer counts, so its venue can be deleted/re-levelled."""
    from calendar_app.models import Competition

    return Competition.objects.filter(
        is_deleted=False, location__path__startswith=location.path, location__is_deleted=False
    ).exists()


def location_can_be_deleted(location) -> bool:
    """A location may be soft-deleted only when nothing live hangs off it: no non-deleted
    descendants and no competitions in its subtree. Otherwise deleting it would orphan those
    children/competitions under a vanished ancestor (review: structural soft-delete)."""
    if _subtree_descendants(location, include_deleted=False).exists():
        return False
    return not location_subtree_has_live_competitions(location)


def location_subtree_is_nonempty(location) -> bool:
    """True if ``location`` has any physical descendant (deleted or not) or a competition in its
    subtree. A level change re-levels the whole physical subtree, so even soft-deleted children
    must block it (a deleted child still moves, and could resurface deeper than depth 4)."""
    if _subtree_descendants(location, include_deleted=True).exists():
        return True
    return location_subtree_has_live_competitions(location)


def soft_delete_location(location) -> None:
    """Atomically soft-delete ``location``. Locks the row (``select_for_update``) and re-checks
    under the lock that nothing live hangs off it, so a child/competition created concurrently
    (``add_location_child`` locks the same row) can't be orphaned. Raises ``LocationConflictError``
    if it can no longer be deleted (already gone, or a live child/competition appeared)."""
    with transaction.atomic():
        _lock_tree_mutation_namespace()
        try:
            locked = Location.objects.select_for_update().get(pk=location.pk, is_deleted=False)
        except Location.DoesNotExist:
            raise LocationConflictError("Location already deleted") from None
        if locked.is_system_fallback:
            raise LocationConflictError("System fallback locations cannot be deleted")
        if not location_can_be_deleted(locked):
            raise LocationConflictError("Location is no longer empty")
        locked.is_deleted = True
        locked.save(update_fields=["is_deleted"])


def _safe_move(location, target, pos: str) -> None:
    # modeltranslation's _rewrite_f() mutates Length() expression objects, which became read-only
    # properties in Django 4+, crashing treebeard's bulk path update during move(). We temporarily
    # make it a no-op for expression types it cannot rewrite.
    import unittest.mock

    from modeltranslation.manager import MultilingualQuerySet

    orig = MultilingualQuerySet._rewrite_f

    def _patched(self, q):  # type: ignore[misc]
        try:
            return orig(self, q)
        except AttributeError:
            return q

    with _MODELTRANSLATION_PATCH_LOCK:
        with unittest.mock.patch.object(MultilingualQuerySet, "_rewrite_f", _patched):
            location.move(target, pos=pos)


def _lock_move_nodes(location, new_parent):
    """Lock and revalidate the nodes participating in a move in a stable order."""
    pks = {location.pk}
    if new_parent is not None:
        pks.add(new_parent.pk)
    rows = {loc.pk: loc for loc in Location.objects.select_for_update().filter(pk__in=pks).order_by("pk")}
    locked = rows.get(location.pk)
    if locked is None:
        raise LocationConflictError("Location no longer exists")
    if new_parent is None:
        return locked, None

    locked_target = rows.get(new_parent.pk)
    if locked_target is None:
        raise LocationConflictError("Location no longer exists")
    if locked_target.is_deleted:
        raise LocationConflictError("Target parent was removed")
    if locked_target.pk == locked.pk or locked_target.is_descendant_of(locked):
        raise LocationConflictError("Target parent is inside the moved subtree")
    return locked, locked_target


def move_location(location, new_parent) -> None:
    """Atomically re-parent (and re-level) ``location`` under ``new_parent`` (``None`` re-roots it
    as a country). Locks the moved node and the target parent (in pk order, to avoid deadlocks
    between two moves) and re-validates everything under those locks -- the target still exists and
    is live, the resulting depth fits the four-level tree, the target isn't inside the moved subtree
    (cycle), and a level change only happens on an empty subtree. So a concurrent delete/move of
    either node can't leave a live node under a removed parent, push it past depth 4, or form a
    cycle. Raises ``LocationConflictError`` otherwise; a no-op when the parent is unchanged."""
    with transaction.atomic():
        _lock_tree_mutation_namespace()
        locked, locked_target = _lock_move_nodes(location, new_parent)

        new_depth = (locked_target.depth + 1) if locked_target is not None else 1
        if new_depth > 4:
            raise LocationConflictError("Resulting depth exceeds the four-level tree")
        if new_depth != locked.depth and location_subtree_is_nonempty(locked):
            raise LocationConflictError("Subtree changed under the node")

        current_parent = locked.get_parent()
        current_pk = current_parent.pk if current_parent is not None else None
        new_pk = locked_target.pk if locked_target is not None else None
        if new_pk == current_pk:
            return
        if locked.is_system_fallback:
            raise LocationConflictError("System fallback locations cannot be moved")
        if locked_target is None:
            # Become a root by joining an existing root as a sorted sibling.
            root = Location.objects.filter(is_deleted=False, depth=1).exclude(pk=locked.pk).order_by("path").first()
            if root is not None:
                _safe_move(locked, root, pos="sorted-sibling")
        else:
            _safe_move(locked, locked_target, pos="sorted-child")


def _build_map_locations(all_locs, candidates=None) -> list:
    """Map markers (issue #113): each location at its own coordinates, or at the nearest
    ancestor with coordinates when it is hidden or has none (see ``map_display_node``).
    Deduplicated so a place isn't drawn twice (its own marker + a resolved child).

    ``candidates`` (defaults to ``all_locs``) are the nodes to draw; ancestor resolution still
    uses the full ``all_locs`` lookup, so filtering the drawn set to a subtree never hides a
    coordinate-less node's resolved ancestor (issue: filtering blanked such markers)."""
    by_path = {loc.path: loc for loc in all_locs}
    step = Location.steplen
    data: list = []
    seen: set = set()
    for loc in all_locs if candidates is None else candidates:
        display = map_display_node(loc, by_path, step)
        if display is None:
            continue
        key = (str(display.lat), str(display.lng), display.name)
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "id": display.pk,
            "name": display.name,
            "lat": float(display.lat),
            "lng": float(display.lng),
            "is_hidden": display.is_hidden,
        }
        data.append(entry)
    return data


def selectable_parent_locations(user=None):
    """Depth 1-3 nodes a user may pick as a parent in the location form: not deleted and either
    public (no proposal or an approved one) or the user's own pending proposal. Excludes other
    users' pending proposals so nobody can build under -- or even see -- a foreign pending node."""
    visible = models.Q(proposal__isnull=True) | models.Q(proposal__status=LocationProposal.Status.APPROVED)
    if user is not None and getattr(user, "is_authenticated", False):
        visible |= models.Q(proposal__status=LocationProposal.Status.PENDING_APPROVAL, proposal__submitted_by=user)
    return Location.objects.filter(is_deleted=False, depth__in=[1, 2, 3]).filter(visible).order_by("path")


def location_filter_rank(row) -> int:
    """Sort priority for a node in the cascade filter dropdowns: visible-with-coordinates
    first, then visible-without-coordinates, then hidden-with-coordinates, then
    hidden-without-coordinates. ``row`` is a dict with ``is_hidden``/``lat``/``lng``."""
    has_coords = row.get("lat") is not None and row.get("lng") is not None
    if not row["is_hidden"]:
        return 0 if has_coords else 1
    return 2 if has_coords else 3


def sort_locations_for_filter(rows) -> list:
    """Stable-sort path-ordered filter rows so hidden / coordinate-less nodes sink to the end
    of every dropdown. The cascade builds each level's options by filtering this list while
    preserving order, so sorting here orders the options (issue: hidden nodes shown last)."""
    return sorted(rows, key=location_filter_rank)


def locations_filter_data(user=None, include_all=False) -> list:
    """Location nodes (pk/depth/path/names/coords) for the country->region->city->location
    cascade filter, in the same shape the calendar list filter consumes. Pending locations are
    visible only to the user who proposed them, unless ``include_all`` (the manager management
    list, which shows every non-deleted row and must be searchable on all of them). Hidden /
    coordinate-less nodes are ordered last within each dropdown level (see
    ``sort_locations_for_filter``)."""
    qs = Location.objects.filter(is_deleted=False)
    if not include_all:
        visible = models.Q(proposal__isnull=True) | models.Q(proposal__status=LocationProposal.Status.APPROVED)
        if user is not None and getattr(user, "is_authenticated", False):
            visible |= models.Q(proposal__status=LocationProposal.Status.PENDING_APPROVAL, proposal__submitted_by=user)
        qs = qs.filter(visible)
    rows = list(
        qs.order_by("path").values("pk", "depth", "path", "name_ru", "name_kk", "name_en", "is_hidden", "lat", "lng")
    )
    for row in rows:
        row["lat"] = float(row["lat"]) if row["lat"] is not None else None
        row["lng"] = float(row["lng"]) if row["lng"] is not None else None
    return sort_locations_for_filter(rows)


def filter_descendant_pks(location_ids) -> set:
    """Union of descendant pks (incl. self) for the selected filter ids. Each value may be a
    comma-joined group of same-name ids (as the multi-select cascade emits)."""
    ids: set[int] = set()
    for value in location_ids or []:
        for part in str(value).split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
    if not ids:
        return set()
    pks: set[int] = set()
    for loc in Location.objects.filter(pk__in=ids, is_deleted=False):
        pks.update(loc.get_descendants(include_self=True).values_list("pk", flat=True))
    return pks


class LocationsMapPage(AsciiSlugMixin, Page):
    intro = RichTextField(blank=True)

    content_panels: ClassVar[list] = [*Page.content_panels, FieldPanel("intro")]

    parent_page_types: ClassVar[list] = ["home.HomePage"]
    subpage_types: ClassVar[list] = []

    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]

    def get_context(self, request):
        from accounts.models import User

        context = super().get_context(request)
        admin_rank = User.ROLE_HIERARCHY.index(User.Role.ADMIN)
        participant_rank = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)
        can_manage = request.user.is_authenticated and (
            request.user.is_superuser or request.user.get_role_rank() >= admin_rank
        )
        all_locs = list(
            Location.objects.filter(is_deleted=False).filter(
                models.Q(proposal__isnull=True) | models.Q(proposal__status=LocationProposal.Status.APPROVED)
            )
        )
        # The cascade filter (shown to managers above the map) narrows the map markers too:
        # selecting a node keeps only that node and its descendants. Pass the narrowed set as the
        # drawn ``candidates`` but keep the full ``all_locs`` for ancestor resolution, so filtering
        # by a coordinate-less city/venue still resolves to its ancestor's coordinates.
        location_ids = request.GET.getlist("location")
        filter_pks = filter_descendant_pks(location_ids) if location_ids else None
        candidates = [loc for loc in all_locs if loc.pk in filter_pks] if filter_pks is not None else None
        context["locations_data"] = _build_map_locations(all_locs, candidates=candidates)
        # Only confirmed users (participant+) may propose a location, so only they see the
        # "Add location" button - a guest would otherwise click through to a 403 (issue #118).
        context["can_add"] = request.user.is_authenticated and (
            request.user.is_superuser or request.user.get_role_rank() >= participant_rank
        )
        context["can_manage"] = can_manage
        if can_manage:
            # Managers get a paginated, filterable list (same UX as the calendar list) instead
            # of the full location dump. The cascade filter narrows by selected node + descendants.
            qs = Location.objects.filter(is_deleted=False).select_related("fallback_identity").order_by("path")
            if filter_pks is not None:
                qs = qs.filter(pk__in=filter_pks)
            paginator = Paginator(qs, 20)
            context["locations_page"] = paginator.get_page(request.GET.get("page", 1))
            # The management table lists every non-deleted node (incl. other users' pending), so
            # the search cascade must cover all of them to stay consistent with what's shown.
            context["filter_locations_data"] = locations_filter_data(request.user, include_all=True)
        return context

    class Meta:
        verbose_name = "Locations map page"
