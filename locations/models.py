import threading
from typing import ClassVar

from django.apps import apps
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


class LocationPendingError(Exception):
    """An action was refused because the location it targets is still awaiting review."""


class LocationInUseError(LocationConflictError):
    """Rejecting a proposed region/city was refused: approved work already sits inside its subtree,
    so clearing the branch would destroy something a moderator or an organizer had blessed."""


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


# The catch-all nodes at every level ("Other country" / "Other region" / "Other city" / "Other
# location") are pinned to the end of their list with this sort_order; real nodes stay below it.
CATCH_ALL_SORT_ORDER = 9999

# Ranks a node above every sibling (including a catch-all) while it is being moved, so
# treebeard's sorted move appends instead of shifting the siblings' paths.
_MOVE_SORT_ORDER = 30000


def next_sort_order(siblings) -> int:
    """The sort_order a new sibling gets: after every real one, still ahead of the catch-all.

    Lists are ordered by sort_order, and the field defaults to 0, so a node added without one would
    jump to the top of its level. Numbering it past the last real sibling appends it where a reader
    expects a new entry, and the catch-all stays last because it sits at ``CATCH_ALL_SORT_ORDER``.
    """
    used = [node.sort_order for node in siblings if node.sort_order < CATCH_ALL_SORT_ORDER]
    return min(max(used) + 1, CATCH_ALL_SORT_ORDER - 1) if used else 1


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
        kwargs.setdefault("sort_order", next_sort_order(siblings))
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


def location_visible_to(location, user) -> bool:
    """Whether ``user`` may see (and therefore build under) ``location``.

    A pending proposal belongs to its proposer until a moderator approves it: everyone else must not
    see it, must not be able to attach anything to it, and must not be able to probe for it.
    """
    proposal = getattr(location, "proposal", None)
    if proposal is None or proposal.status != LocationProposal.Status.PENDING_APPROVAL:
        return True
    if can_manage_locations(user):
        return True
    return bool(getattr(user, "is_authenticated", False)) and proposal.submitted_by_id == getattr(user, "pk", None)


def chain_is_approved(parent) -> bool:
    """Whether ``parent`` and everything above it is public, so a child may land approved.

    A venue is the one level an organizer adds without review -- but only inside geography a
    moderator has blessed. Approving it under their own pending city would publish that city's name
    through the competition attached to it, and would then block the city's rejection for good.
    """
    if parent is None:
        return True
    return not any(node.is_pending for node in [parent, *parent.get_ancestors()])


def can_manage_locations(user) -> bool:
    """Whether ``user`` may bless geography (approve/reject a location proposal): ADMIN+ only.

    Competitions are moderated a rung lower, by ORGANIZER+, so this is what keeps approving an event
    from quietly approving the region and city proposed with it. ``locations.views`` mirrors it.
    """
    from accounts.models import User

    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False)) or user.get_role_rank() >= User.ROLE_HIERARCHY.index(
        User.Role.ADMIN
    )


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
                sort_order=CATCH_ALL_SORT_ORDER,  # the catch-all venue stays last in its city
            )
            LocationFallback.objects.create(city=locked_city, location=fallback)
            return fallback

    _LEVEL_LABELS: ClassVar[dict] = {1: "Country", 2: "Region", 3: "City", 4: "Venue"}

    def get_level_label(self) -> str:
        """The node's level as a word, for a moderator deciding what a proposal actually is."""
        return gettext(self._LEVEL_LABELS.get(self.depth, "Location"))

    @property
    def ancestor_label(self) -> str:
        """The chain above this node, so a proposed "Almaty" can be told apart from another one."""
        return ", ".join(node.name for node in self.get_ancestors())

    def _approve_system_fallback(self) -> None:
        """Approve the city's catch-all venue alongside the city itself.

        The catch-all is created pending when its city is, and it is shared by everyone, so leaving
        it pending would make a public city's shared venue one user's private property.
        """
        try:
            mapping = self.fallback_mapping
        except LocationFallback.DoesNotExist:
            return
        mapping.location._approve_proposal()

    def _approve_proposal(self) -> None:
        proposal = getattr(self, "proposal", None)
        if proposal is not None and proposal.status != LocationProposal.Status.APPROVED:
            proposal.status = LocationProposal.Status.APPROVED
            proposal.save(update_fields=["status"])

    def approve_with_competition(self, reviewer=None) -> None:
        """Auto-approve this pending location when its competition is approved.

        A venue can be proposed together with the city (and region) holding it, and leaving those
        pending would keep the approved competition's branch out of everyone else's location filter.
        So the pending ancestors are approved too -- but only for a reviewer who may bless geography
        (ADMIN+). An organizer moderating an event may approve the venue, which is a level they can
        create outright anyway; the region and city stay in the admin's queue instead of being waved
        through by someone the API would not let create them.
        """
        if can_manage_locations(reviewer):
            for node in [self, *self.get_ancestors()]:
                node._approve_proposal()
                node._approve_system_fallback()
            return
        # An organizer may bless the venue only where the geography above it is already public.
        # Approving it under a pending city would publish that city through the competition and
        # then block the city's rejection for good, since the branch would hold approved work.
        if chain_is_approved(self.get_parent()):
            self._approve_proposal()

    def _reject_proposed_place(self) -> None:
        """Clear a rejected region/city, refusing when anything approved lives inside it.

        Runs inside the caller's transaction and tree lock. The subtree rows are locked *before* any
        competition is touched, which is the order every competition write already takes (its
        location row, then the competition). That ordering is what stops a concurrent submission
        from binding to a node that is about to disappear, and stops the two paths deadlocking.

        Unlike a venue there is no stand-in to hand the competitions to, so they lose their location
        and a human re-places them -- but only ones that are still drafts or awaiting review. A
        published competition, or a descendant a moderator has already approved, means the branch is
        no longer just a proposal, and the rejection is refused instead of destroying it.
        """
        competition_cls = apps.get_model("calendar_app", "Competition")
        subtree = list(
            Location.objects.select_for_update().filter(path__startswith=self.path, is_deleted=False).order_by("path")
        )
        # Lock the descendants' proposals as well, and judge on what the lock returns rather than on
        # the status loaded with the node: approving one writes only the proposal row, so an unlocked
        # read lets a concurrent approval slip between this check and the delete below, destroying a
        # branch this method promised to spare.
        pending = {
            proposal.location_id
            for proposal in LocationProposal.objects.select_for_update()
            .filter(location__in=subtree, status=LocationProposal.Status.PENDING_APPROVAL)
            .order_by("pk")
        }
        for node in subtree:
            if node.pk not in pending and not node.is_system_fallback:
                raise LocationInUseError("Location proposal holds an approved location")
        pks = [node.pk for node in subtree]
        # Lock the competitions before reading their status. Approving a competition only takes a
        # row lock when it writes, so without this the check and the update below straddle a window
        # in which a moderator can publish one -- and the update would then blank the location of a
        # competition this method promises to refuse.
        live = list(competition_cls.objects.select_for_update().filter(is_deleted=False, location_id__in=pks))
        # A rejected competition is exactly what a moderator clears before rejecting the geography
        # invented for it, so it must not stand in the way. Anything else with real content -- a
        # published event, or one carrying registrations even after being demoted back to pending --
        # is not disposable: refuse rather than silently blank its location.
        disposable = (
            competition_cls.Status.DRAFT,
            competition_cls.Status.PENDING_APPROVAL,
            competition_cls.Status.REJECTED,
        )
        for competition in live:
            if competition.status not in disposable:
                raise LocationInUseError("Location proposal is used by a published competition")
            if competition.registrations.exists():
                raise LocationInUseError("Location proposal is used by a competition with registrations")

        competition_cls.objects.filter(pk__in=[competition.pk for competition in live]).update(location=None)
        # The catch-all venues in the subtree go with it, so their identity rows must not outlive it.
        LocationFallback.objects.filter(models.Q(city_id__in=pks) | models.Q(location_id__in=pks)).delete()
        Location.objects.filter(pk__in=pks).update(is_deleted=True)

    def reject_and_reset_competitions(self) -> None:
        """Atomically reject a pending location and deal with the competitions that used it.

        A rejected venue hands its competitions to its city's catch-all venue, so they stay on the
        map. A rejected region or city has no such stand-in -- the branch itself is what the reviewer
        refused -- so the whole subtree goes and the competitions inside it lose their location for a
        human to set.
        """
        with transaction.atomic():
            _lock_tree_mutation_namespace()
            parent = self.get_parent()
            if parent is None:
                raise LocationConflictError("Proposed location no longer has a parent")

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

            if locked.depth < 4:
                locked._reject_proposed_place()
                return
            if locked.is_system_fallback:
                # A city's catch-all is not a proposal to judge on its own: it exists for as long as
                # its city does, and handing its competitions to "the city's catch-all" would hand
                # them back to itself before soft-deleting it out from under them.
                raise LocationInUseError("A city's catch-all venue is rejected with its city")

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
        # An approved node must not slide under a branch still awaiting review: the branch would
        # then hold public work and could never be rejected, and list_locations would drop the
        # approved node along with its invisible parent. This mirrors every create path's rule.
        # Judge on proposal rows locked under the tree lock, not on the status the node was loaded
        # with -- a concurrent approve writes only the proposal row and would otherwise slip through.
        if locked_target is not None:
            chain = [locked, locked_target, *locked_target.get_ancestors()]
            still_pending = set(
                LocationProposal.objects.select_for_update()
                .filter(location__in=chain, status=LocationProposal.Status.PENDING_APPROVAL)
                .values_list("location_id", flat=True)
            )
            moving_approved = locked.pk not in still_pending
            target_chain_pending = any(
                node.pk in still_pending for node in [locked_target, *locked_target.get_ancestors()]
            )
            if moving_approved and target_chain_pending:
                raise LocationConflictError("Cannot move an approved location under a pending one")
        if new_depth != locked.depth and location_subtree_is_nonempty(locked):
            raise LocationConflictError("Subtree changed under the node")

        current_parent = locked.get_parent()
        current_pk = current_parent.pk if current_parent is not None else None
        new_pk = locked_target.pk if locked_target is not None else None
        if new_pk == current_pk:
            return
        if locked.is_system_fallback:
            raise LocationConflictError("System fallback locations cannot be moved")
        # treebeard only allows a *sorted* move while node_order_by is set, and a sorted insert
        # assumes a sibling's path order matches its sort order. The seeds deliberately break that
        # (a capital carries sort_order 1 at an appended path), and inserting in the middle then
        # shifts later siblings straight into the unique path index -- a 500 on an ordinary edit.
        # Ranking the node above every sibling for the duration makes the sorted move land at the
        # end, which shifts nothing; its real place in the listing is restored right after, by an
        # UPDATE that touches sort_order only and leaves every path alone.
        Location.objects.filter(pk=locked.pk).update(sort_order=_MOVE_SORT_ORDER)
        locked.sort_order = _MOVE_SORT_ORDER
        if locked_target is None:
            # Become a root by joining an existing root as a sorted sibling.
            root = Location.objects.filter(is_deleted=False, depth=1).exclude(pk=locked.pk).order_by("path").first()
            if root is not None:
                _safe_move(locked, root, pos="sorted-sibling")
        else:
            _safe_move(locked, locked_target, pos="sorted-child")
        # treebeard's move() leaves the in-memory node stale, so read the new depth from the target
        # rather than from ``locked``: re-rooting used to compare against every node at the node's
        # *old* depth, which handed the new country the global maximum and sorted it past them all.
        new_depth = 1 if locked_target is None else locked_target.depth + 1
        siblings = Location.objects.filter(depth=new_depth).exclude(pk=locked.pk)
        if locked_target is not None:
            siblings = siblings.filter(path__range=Location._get_children_path_interval(locked_target.path))
        Location.objects.filter(pk=locked.pk).update(sort_order=next_sort_order(list(siblings)))


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
    qs = Location.objects.filter(is_deleted=False, depth__in=[1, 2, 3])
    if can_manage_locations(user):
        # A moderator has to reach the very nodes they are reviewing: without this they cannot fix a
        # misspelt proposed city, nor add anything inside it, and the queue becomes a dead end.
        return qs.order_by("sort_order", "path")
    visible = models.Q(proposal__isnull=True) | models.Q(proposal__status=LocationProposal.Status.APPROVED)
    if user is not None and getattr(user, "is_authenticated", False):
        visible |= models.Q(proposal__status=LocationProposal.Status.PENDING_APPROVAL, proposal__submitted_by=user)
    return qs.filter(visible).order_by("sort_order", "path")


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
        qs.order_by("sort_order", "path").values(
            "pk", "depth", "path", "name_ru", "name_kk", "name_en", "is_hidden", "lat", "lng"
        )
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
            # Path order, not sort_order: this table is a flat page through the whole tree, so it
            # has to read as a hierarchy (a country, then its regions, then their cities). sort_order
            # only ranks siblings, and sorting the whole tree by it interleaves depths and branches --
            # every country's capital would float to the top, ahead of the countries themselves. The
            # cascade dropdowns are different: they are filtered to one parent, where sort_order is
            # exactly the right answer.
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
