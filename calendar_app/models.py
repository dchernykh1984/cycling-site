import datetime
import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from wagtail.search import index

from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
from cycling_site.sanitize import sanitize_rich_text_columns

# Rich-text description fields sanitized on every write whatever the entry point (organizer
# form, API, Django admin, Wagtail snippet). Includes the canonical ``description``: the API
# writes a raw value straight into that column and localize_field() serves it as the fallback
# for empty translations, so it must be sanitized too. All four are accessed via __dict__ in
# save() so we touch the concrete columns directly and never go through modeltranslation's
# canonical descriptor (whose getter returns another language's fallback for an empty
# translation, which would otherwise copy e.g. the RU body into an empty KK column).
_DESCRIPTION_FIELDS = ("description", "description_ru", "description_kk", "description_en")

# Backwards-compatible alias for the shared, site-wide rich-text size cap (organizer form + API).
MAX_DESCRIPTION_LENGTH = MAX_RICH_TEXT_LENGTH


class EventType(models.Model):
    objects: ClassVar[models.Manager["EventType"]]
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list] = ["order"]
        verbose_name = "Event type"
        verbose_name_plural = "Event types"

    def __str__(self) -> str:
        return self.name or f"EventType #{self.pk}"


def usual_event_type_id() -> int | None:
    """The event type first in the list's order, which an event's description leaves unsaid (issue #334).

    Most events are of that kind, so naming it would only lengthen every description; the rule
    follows the order the types are kept in, not a name written here.
    """
    return EventType.objects.order_by("order", "pk").values_list("pk", flat=True).first()


class DisciplineCategory(models.Model):  # type: ignore[django-manager-missing]
    objects: ClassVar[models.Manager["DisciplineCategory"]]
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list] = ["order"]
        verbose_name = "Discipline category"
        verbose_name_plural = "Discipline categories"

    def __str__(self) -> str:
        return self.name or f"DisciplineCategory #{self.pk}"


class Discipline(models.Model):
    objects: ClassVar[models.Manager["Discipline"]]
    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        "DisciplineCategory",
        on_delete=models.PROTECT,
        related_name="disciplines",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list] = ["category__order", "order"]
        verbose_name = "Discipline"
        verbose_name_plural = "Disciplines"

    def __str__(self) -> str:
        return self.name or f"Discipline #{self.pk}"


class Competition(index.Indexed, models.Model):
    objects: ClassVar[models.Manager["Competition"]]

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # A start is often more than one thing at once: a race with a kids race inside it, or an open
    # mass start that also holds a professional field. One type per event forced those to be filed
    # as two events or as neither, so an event carries a set of types the way it carries a set of
    # disciplines. Nothing requires more than one.
    event_types: models.ManyToManyField = models.ManyToManyField(
        "EventType",
        blank=True,
        related_name="competitions",
    )
    disciplines: models.ManyToManyField = models.ManyToManyField(
        "Discipline",
        blank=True,
        related_name="competitions",
    )
    location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="competitions",
    )
    date_start = models.DateField()
    date_end = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        db_index=True,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # When its page last changed, for the sitemap's lastmod (#348). Empty for events last edited
    # before the field existed; a save that names its fields leaves it alone unless it names it too.
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    url_route = models.URLField(blank=True)
    url_announcement = models.URLField(blank=True)
    url_registration = models.URLField(blank=True)
    url_regulations = models.URLField(blank=True)
    url_results = models.URLField(blank=True)
    file_announcement = models.FileField(upload_to="competitions/announcements/", blank=True)
    file_regulations = models.FileField(upload_to="competitions/regulations/", blank=True)
    file_route = models.FileField(upload_to="competitions/routes/", blank=True)
    file_results = models.FileField(upload_to="competitions/results/", blank=True)
    # The picture a chat shows when somebody pastes a link to this event. Optional: without one the
    # page falls back to the site mark, which is what every event showed before. Whatever is
    # uploaded is re-encoded and bounded on the way in (calendar_app.preview_image), so what lands
    # here is always a plain image of a predictable size with no camera metadata on it.
    preview_image = models.ImageField(upload_to="competitions/preview/", blank=True)
    # The line a chat shows under the title when somebody pastes a link to this event -- the
    # meeting time and place, say, which the generated summary cannot know. Optional, translated
    # like the title; without it the page keeps describing itself with search_summary(). Bounded
    # because a chat shows a line or two and cuts the rest.
    preview_text = models.CharField(max_length=200, blank=True)
    # Secret credential for the offline timing tools. Nullable so a manager can delete it (revoke
    # all timing access) if it leaks; a new one is minted by the regenerate action.
    upload_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, null=True, blank=True)

    # --- Registration feature ---
    registration_enabled = models.BooleanField(default=False)

    class RegistrationMode(models.TextChoices):
        SELF_ONLY = "self_only", "Self only (linked to user account)"
        FREE = "free", "Free (can register any person)"

    registration_mode = models.CharField(
        max_length=20,
        choices=RegistrationMode.choices,
        default=RegistrationMode.SELF_ONLY,
        blank=True,
    )

    class BirthDateMode(models.TextChoices):
        YEAR = "year", "Year of birth"
        DATE = "date", "Full birth date"

    birth_date_mode = models.CharField(
        max_length=10,
        choices=BirthDateMode.choices,
        default=BirthDateMode.YEAR,
        blank=True,
    )

    require_approval = models.BooleanField(default=False)
    require_payment = models.BooleanField(default=False)
    allow_multiple_registrations = models.BooleanField(default=False)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)

    show_unapproved_in_list = models.BooleanField(default=False)
    show_unpaid_in_list = models.BooleanField(default=False)
    show_approval_status_col = models.BooleanField(default=False)
    show_payment_status_col = models.BooleanField(default=False)

    class AdditionalInfoMode(models.TextChoices):
        NONE = "none", "Do not show"
        FREE = "free", "Free-form input"
        STRAVA = "strava", "Strava link"

    additional_info_mode = models.CharField(
        max_length=10,
        choices=AdditionalInfoMode.choices,
        default=AdditionalInfoMode.FREE,
        blank=True,
    )
    # Whether the additional-info column is shown in the public participant list. Managers
    # always see it; this only hides it from everyone else (e.g. keep Strava links private).
    show_additional_info_in_list = models.BooleanField(default=True)
    # Whether filling the additional-info field is mandatory at registration. Only meaningful
    # when the field is shown (mode != none); existing competitions default to optional.
    additional_info_required = models.BooleanField(default=False)
    # What the additional-info field is called on the registration form and in the participant
    # list. Organizers collect very different things in it -- a bike type, a transfer preference,
    # a shirt size -- and "Additional info" tells the rider none of that. One string rather than
    # three: the organizer writes the wording they use with their own riders.
    additional_info_label = models.CharField(max_length=100, blank=True)

    relay_enabled = models.BooleanField(default=False)
    relay_max_members = models.PositiveIntegerField(default=10)

    # Permanent lock: True once registration is first activated; never reset to False.
    registration_mode_locked = models.BooleanField(default=False)

    is_hidden = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    # Invite-only (issue #313): published, but only to the people who may edit it and to everyone
    # who has opened its invitation link while signed in. Not the same as is_hidden, which takes an
    # event down for everybody; the two combine, and a hidden event stays hidden from invitees too.
    invite_only = models.BooleanField(default=False, db_index=True)
    # A top event goes first wherever events are listed -- at the head of the list above a divider,
    # first in its day on the calendar, first at its place on the map. Admins and the owner set it.
    is_top = models.BooleanField(default=False)
    # The secret in the invitation link. Issued when the event first becomes invite-only rather than
    # by a column default: a default is evaluated once for every existing row in the migration, and
    # one key shared by every old event would open each of them with any other's link.
    invite_key = models.UUIDField(null=True, blank=True, editable=False)

    search_fields: ClassVar[list] = [
        index.SearchField("title_ru"),
        index.SearchField("title_kk"),
        index.SearchField("title_en"),
        index.SearchField("description_ru"),
        index.SearchField("description_kk"),
        index.SearchField("description_en"),
        index.FilterField("status"),
        index.FilterField("is_deleted"),
        index.FilterField("is_hidden"),
    ]

    class Meta:
        ordering: ClassVar[list] = ["date_start"]
        verbose_name = "Competition"
        verbose_name_plural = "Competitions"

    def __str__(self) -> str:
        return self.title or f"Competition #{self.pk}"

    def save(self, *args, **kwargs):
        # Descriptions are stored as rich HTML and rendered with |safe, so sanitize them on
        # every write -- the single choke point covering the organizer form, the API, Django
        # admin and Wagtail snippets (see _DESCRIPTION_FIELDS for the __dict__ rationale).
        update_fields = kwargs.get("update_fields")
        sanitize_rich_text_columns(self, _DESCRIPTION_FIELDS, update_fields=update_fields)
        # Only a save that writes the status can move the event through review.
        stored = None
        moved = False
        if update_fields is None or "status" in update_fields:
            if not self._state.adding:
                stored = type(self).objects.filter(pk=self.pk).values("status", "approved_by_id", "approved_at").first()
            moved = stored is None or stored["status"] != self.status
        changed = self._record_reviewer(stored) if moved else set()
        if self.invite_only and self.invite_key is None:
            self.invite_key = uuid.uuid4()
            changed.add("invite_key")
        if update_fields is not None and changed:
            kwargs["update_fields"] = {*update_fields, *changed}
        super().save(*args, **kwargs)
        if moved:
            self._log_status_change(stored)

    def get_absolute_url(self) -> str:
        """Where this competition lives. Needed by the sitemap, and by anything that has a
        competition in hand and wants to link to it without knowing the URL layout."""
        return reverse("competition_detail", kwargs={"pk": self.pk})

    def _record_reviewer(self, stored) -> set[str]:
        """Note who approved or rejected the event and when, on its way into that status, whatever door it took.

        The moderation page sets both; the status field of the Wagtail admin and an admin's event
        created through the API set neither, so an event could be published with no trace of who
        did it (#741). The reviewer is the signed-in user of the request, or the API token's holder.
        Called only on a save that moves the event to another status: whoever approved an event
        that is already approved is unknown, and the person editing it now is not them.
        """
        if self.status not in (self.Status.APPROVED, self.Status.REJECTED):
            return set()
        # What the row already held was not set for this review: a rejection keeps its reviewer in
        # the same two fields, and an event approved by hand afterwards would credit them.
        by_set = self.approved_by_id is not None and (stored is None or self.approved_by_id != stored["approved_by_id"])
        at_set = self.approved_at is not None and (stored is None or self.approved_at != stored["approved_at"])
        from audit.middleware import get_current_user

        changed = set()
        if not by_set:
            user = get_current_user()
            self.approved_by = user if getattr(user, "is_authenticated", False) else None
            changed.add("approved_by")
        if not at_set:
            self.approved_at = timezone.now()
            changed.add("approved_at")
        return changed

    def _log_status_change(self, stored) -> None:
        """Add this save's step to the event's way through review: its new status, who moved it, when."""
        from audit.middleware import get_current_user

        user = get_current_user()
        by = user.pk if getattr(user, "is_authenticated", False) else None
        if stored is None:
            by = self.submitted_by_id or by
        elif self.status in (self.Status.APPROVED, self.Status.REJECTED):
            by = self.approved_by_id
        CompetitionStatusChange.objects.create(
            competition=self,
            added=stored is None,
            status=self.status,
            previous_status=stored["status"] if stored else "",
            changed_by_id=by,
            reason=self.rejection_reason if self.status == self.Status.REJECTED else "",
        )

    def regenerate_invite_key(self) -> None:
        """Issue a new invitation link. The old one stops working; people already let in stay in."""
        self.invite_key = uuid.uuid4()
        self.save(update_fields=["invite_key"])

    def search_summary(self, usual_type_id: int | None = None) -> str:
        """One sentence about this event, for the page's meta description.

        Built from the facts a search result needs -- what, when, where, which sport -- rather than
        from the organizer's HTML, which is often several screens of regulations and starts with a
        greeting. Every competition page used to carry the same site-wide sentence, which told a
        search engine nothing that distinguished one race from another.

        Its kind follows, unless it is the usual one (``usual_type_id``, looked up when not given:
        a feed of many events looks it up once), and a direction's catch-all discipline reads as
        its direction -- "Road Cycling", not "Other (Road Cycling)" (issue #334).
        """
        from django.utils.formats import date_format
        from django.utils.translation import gettext as _

        from .listing_seo import CATCH_ALL_DISCIPLINE_PREFIX

        when = date_format(self.date_start, "j E Y")
        if self.date_end and self.date_end != self.date_start:
            when = f"{when} - {date_format(self.date_end, 'j E Y')}"
        where = ", ".join(part for part in (self.city_label, self.country_label) if part)
        usual = usual_type_id if usual_type_id is not None else usual_event_type_id()
        types = ", ".join(t.name for t in self.event_types.all() if t.pk != usual)
        names: list[str] = []
        for d in self.disciplines.all():
            name = d.category.name if (d.name_en or "").startswith(CATCH_ALL_DISCIPLINE_PREFIX) else d.name
            if name not in names:
                names.append(name)
        kinds = ", ".join(names[:3])

        parts = [f"{self.title}: {when}" + (f", {where}" if where else "") + "."]
        if types:
            parts.append(_("Type: %(types)s.") % {"types": types})
        if kinds:
            parts.append(_("Disciplines: %(kinds)s.") % {"kinds": kinds})
        parts.append(_("Details, start point and results on the Universal Bicycle Team calendar."))
        return " ".join(parts)

    def get_calendar_end(self) -> str | None:
        if self.date_end:
            return (self.date_end + datetime.timedelta(days=1)).isoformat()
        return None

    def approve(self, reviewer) -> None:
        from accounts import roles
        from locations.models import LocationPendingError, chain_is_approved

        if self.status not in (self.Status.PENDING_APPROVAL, self.Status.DRAFT):
            raise ValueError(f"Cannot approve: competition is already '{self.get_status_display()}'.")
        self.status = self.Status.APPROVED
        # Refuse while the event sits on geography this reviewer may not bless. Approving anyway
        # publishes the event on a branch nobody else can see, and the branch then holds approved
        # work -- which leaves an admin no way to reject it, delete it or unwind the event.
        location = self.location
        # Only the geography *above* the venue matters: approving the venue itself is a level an
        # organizer may create outright, and that is the designed flow for a proposed start point.
        if (
            location is not None
            and not roles.at_least(reviewer, roles.APPROVE_PLACES)
            and not chain_is_approved(location.get_parent())
        ):
            raise LocationPendingError(
                "This event's location is still awaiting review; an administrator must approve it first."
            )
        self.approved_by = reviewer
        self.approved_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "approved_by", "approved_at", "rejection_reason"])
        # Approving a competition auto-approves its proposed location (issue #111).
        location = self.location
        if location is not None:
            location.approve_with_competition(reviewer)

    def reject(self, reviewer, reason: str = "") -> None:
        if self.status not in (self.Status.PENDING_APPROVAL, self.Status.DRAFT):
            raise ValueError(f"Cannot reject: competition is already '{self.get_status_display()}'.")
        self.status = self.Status.REJECTED
        self.approved_by = reviewer
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        # Save the status change and its history row together so a failure can't leave one without
        # the other. Every rejection reason is kept as history, surviving edits/resubmissions (#200).
        with transaction.atomic():
            self.save(update_fields=["status", "approved_by", "approved_at", "rejection_reason"])
            CompetitionRejection.objects.create(competition=self, reason=reason, rejected_by=reviewer)

    def resubmit(self) -> None:
        """Send a rejected competition back for a fresh review; the reason history stays intact."""
        if self.status != self.Status.REJECTED:
            raise ValueError(f"Cannot resubmit: competition is '{self.get_status_display()}', not rejected.")
        self.status = self.Status.PENDING_APPROVAL
        self.rejection_reason = ""  # the past reasons remain in self.rejections
        self.approved_by = None
        self.approved_at = None
        self.save(update_fields=["status", "rejection_reason", "approved_by", "approved_at"])

    @property
    def timezone(self):
        """The zone at the event's place, worked out from its location on each use (issue #344).

        Not cached: the edit view moves an event to another place and then reads its zone."""
        from locations.models import timezone_of

        return timezone_of(self.location)

    def is_registration_open(self, ignore_limit: bool = False) -> bool:
        # ``ignore_limit`` lets callers ask only "is the window still open by deadline" -- e.g. a
        # registration owner editing an existing entry already holds a slot, so a full competition
        # must not lock them out.
        if not self.registration_enabled:
            return False
        if self.status != self.Status.APPROVED:
            return False
        if self.registration_deadline:
            if self.registration_deadline < timezone.now():
                return False
        # An event with no deadline of its own used to keep taking entries years after it was
        # ridden. It closes when the race is over instead -- and not a moment earlier, because a
        # start can be in the evening, so the window stands all through the final day -- the day
        # at the event's place, not the reader's.
        elif timezone.localdate(timezone=self.timezone) > (self.date_end or self.date_start):
            return False
        return True if ignore_limit else not self.is_limit_reached()

    def qualified_count(self, category=None) -> int:
        qs = self.registrations.filter(is_rejected=False)
        if category is not None:
            qs = qs.filter(category=category)
        if self.require_approval:
            qs = qs.filter(is_approved=True)
        if self.require_payment:
            qs = qs.filter(is_paid=True)
        return qs.count()

    def is_limit_reached(self, category=None) -> bool:
        if category is not None:
            if category.max_participants is None:
                return False
            return self.qualified_count(category=category) >= category.max_participants
        if self.max_participants is None:
            return False
        return self.qualified_count() >= self.max_participants

    @property
    def show_additional_info_field(self) -> bool:
        """Whether the registration form shows the additional-info field at all."""
        return self.additional_info_mode != self.AdditionalInfoMode.NONE

    @property
    def additional_info_field_label(self) -> str:
        """What to call the additional-info field, in the reader's language when we chose it.

        The organizer's own wording wins when there is one; otherwise the built-in name, which
        depends on what the field collects.
        """
        from django.utils.translation import gettext

        if self.additional_info_label.strip():
            return self.additional_info_label.strip()
        return gettext("Strava link") if self.additional_info_is_strava else gettext("Additional info")

    @property
    def additional_info_is_strava(self) -> bool:
        """Whether the additional-info field collects a Strava link (vs free text)."""
        return self.additional_info_mode == self.AdditionalInfoMode.STRAVA

    @property
    def additional_info_visible_publicly(self) -> bool:
        """Whether the additional-info column shows to non-managers in the participant list."""
        return self.show_additional_info_field and self.show_additional_info_in_list

    @property
    def location_label(self) -> str:
        """Returns a brief display name: skips hidden depth-4 fallback venues."""
        loc = self.location
        if not loc:
            return ""
        if not loc.is_hidden:
            return loc.name
        # Hidden depth-4 fallback venue -> show parent city (depth=3)
        if loc.depth == 4:
            from locations.models import Location  # local import to avoid circular

            step = len(loc.path) // 4
            try:
                return Location.objects.get(path=loc.path[: step * 3], depth=3).name
            except Location.DoesNotExist:
                pass
        return loc.name

    @property
    def place_parts(self) -> list[str]:
        """Where it is, from the start point out -- venue, city, region, country -- each named once.

        One column of the list instead of four, so the table's words fit a desktop (issue #383).
        """
        parts: list[str] = []
        for part in (self.location_label, self.city_label, self.region_label, self.country_label):
            if part and part not in parts:
                parts.append(part)
        return parts

    @property
    def place_label(self) -> str:
        return ", ".join(self.place_parts)

    @property
    def location_full_label(self) -> str:
        """Returns full country-region-city-venue path, comma-separated."""
        loc = self.location
        if not loc:
            return ""
        return ", ".join(n.name for n in [*loc.get_ancestors(), loc])

    @property
    def event_type_label(self) -> str:
        """All attached types, comma-joined (an event can be a race and a kids race at once)."""
        return ", ".join(e.name for e in self.event_types.all() if e.name)

    @property
    def disciplines_label(self) -> str:
        """All attached disciplines, comma-joined (a competition can have several)."""
        return ", ".join(d.name for d in self.disciplines.all() if d.name)

    @property
    def direction_label(self) -> str:
        """Distinct discipline categories (e.g. Road, MTB) - the "directions" used in filters."""
        names: dict[int, str] = {}
        for d in self.disciplines.all():
            if d.category_id and d.category_id not in names and d.category:
                names[d.category_id] = d.category.name
        return ", ".join(names.values())

    @cached_property
    def _location_nodes_by_depth(self) -> dict:
        """Maps tree depth -> location node for this competition's location chain.

        Depth convention: 1=country, 2=region, 3=city, 4=venue.
        """
        loc = self.location
        if not loc:
            return {}
        return {node.depth: node for node in [*loc.get_ancestors(), loc]}

    @property
    def country_label(self) -> str:
        node = self._location_nodes_by_depth.get(1)
        return node.name if node else ""

    @property
    def region_label(self) -> str:
        node = self._location_nodes_by_depth.get(2)
        return node.name if node else ""

    @property
    def city_label(self) -> str:
        node = self._location_nodes_by_depth.get(3)
        return node.name if node else ""


class CompetitionMaterial(models.Model):
    """One named link to photo or video coverage of an event.

    The documents already on a competition (announcement, route, regulations, results) are a fixed
    set of known slots, each with its own meaning. Coverage is not: an event can come back with one
    album or with a photographer's gallery, a drone edit and three riders' onboard videos, and there
    is no telling in advance what any of them should be called. So this is an open-ended list where
    the caption is written by whoever adds the link, and both halves are mandatory -- a link with no
    caption is a button nobody can read, and a caption with no link is a button that does nothing.

    The caption is not translated: it names a specific album the way its author named it, and asking
    for three spellings of "Photos by Ivan" would leave two of them empty on most events.
    """

    objects: ClassVar[models.Manager["CompetitionMaterial"]]

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="materials")
    title = models.CharField(max_length=255)
    url = models.URLField()
    # Position in the list as its author arranged it, renumbered from the form on every save. Ties
    # (rows added in the same edit before the renumbering runs) fall back to insertion order.
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list] = ["order", "pk"]
        verbose_name = "Competition material"

    def __str__(self) -> str:
        return f"{self.title} ({self.url})"


class CompetitionRejection(models.Model):
    """One moderation rejection of a competition, kept as history across resubmissions (#200)."""

    objects: ClassVar[models.Manager["CompetitionRejection"]]

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="rejections")
    reason = models.TextField(blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rejected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list] = ["-rejected_at"]

    def __str__(self) -> str:
        return f"Rejection of competition {self.competition_id} at {self.rejected_at:%Y-%m-%d}"


class CompetitionStatusChange(models.Model):
    """One step of an event's way through review, which admins see at the foot of its page (#741).

    Competition.save() writes one whenever a save moves the event to another status, whatever door
    it took: the moderation page, the API, the Wagtail admin. The first is the event being added.
    Steps from before the history was kept were filled in from what was recorded then -- the audit
    log's entry for the event's creation, the rejections, the last approval -- and a resubmission
    from then is not known.
    """

    objects: ClassVar[models.Manager["CompetitionStatusChange"]]

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="status_changes")
    # The event being added, in the status it was added in; blank for an old one, whose first
    # status nobody recorded.
    added = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=Competition.Status.choices, blank=True)
    previous_status = models.CharField(max_length=30, choices=Competition.Status.choices, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list] = ["changed_at", "pk"]

    def __str__(self) -> str:
        return f"Competition {self.competition_id}: {self.previous_status or '-'} -> {self.status or '-'}"

    @property
    def label(self) -> str:
        from django.utils.translation import gettext as _

        status = Competition.Status
        if self.added:
            added: dict[str, str] = {
                status.PENDING_APPROVAL: _("Added for review"),
                status.APPROVED: _("Added and published"),
                status.DRAFT: _("Added as a draft"),
            }
            return added.get(self.status, _("Added"))
        if self.status == status.PENDING_APPROVAL:
            back: dict[str, str] = {
                status.REJECTED: _("Resubmitted for review"),
                status.APPROVED: _("Returned for review"),
            }
            return back.get(self.previous_status, _("Sent for review"))
        moved: dict[str, str] = {
            status.APPROVED: _("Approved"),
            status.REJECTED: _("Rejected"),
            status.DRAFT: _("Moved to drafts"),
        }
        return moved.get(self.status, self.status)


class CompetitionComment(models.Model):
    objects: ClassVar[models.Manager["CompetitionComment"]]
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="competition_comments",
    )
    body = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list] = ["created_at"]
        verbose_name = "Competition comment"

    def __str__(self) -> str:
        return f"Comment by {self.author} on {self.competition}"


class CompetitionFavorite(models.Model):
    """A per-user "favorite" mark on a competition (issue #183).

    Lets a signed-in user star events they care about and filter the calendar/list/map (and the
    REST list endpoint) down to them. A plain join row -- one per (user, competition) pair -- so a
    user can favorite any number of events and toggling just creates or deletes the row.
    """

    objects: ClassVar[models.Manager["CompetitionFavorite"]]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="competition_favorites",
    )
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Competition favorite"
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["user", "competition"], name="uniq_user_competition_favorite"),
        ]
        indexes: ClassVar[list] = [models.Index(fields=["user", "competition"])]

    def __str__(self) -> str:
        return f"{self.user} favorites {self.competition}"


class CompetitionInvite(models.Model):
    """Somebody let into an invite-only event: they opened its link while signed in (issue #313).

    One row per (competition, user). It outlives a new link, so issuing one to stop a leaked link
    spreading does not throw out the people who were already invited.
    """

    objects: ClassVar[models.Manager["CompetitionInvite"]]
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="invites")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="competition_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Competition invite"
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["competition", "user"], name="uniq_competition_invite"),
        ]

    def __str__(self) -> str:
        return f"{self.user} invited to {self.competition}"


class CompetitionReport(models.Model):
    """A user-submitted report ("this event looks wrong") on a public competition (issue #233).

    Most events are added in bulk by the import agent, so any confirmed participant can flag one they
    believe is inaccurate. A reported event keeps showing to everyone, but also surfaces in the
    moderation queue (like an event on an unapproved location) so an admin can edit, delete, comment,
    or dismiss the report -- there is no "approve" step, the event is already public. ``reported_by``
    is nullable so deleting the reporter's account leaves the report (and its reason) for the admin.
    """

    objects: ClassVar[models.Manager["CompetitionReport"]]
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reason = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Resolved == the report was dismissed by an admin ("mark as fine"); it then drops out of the
    # moderation queue. Deleting or editing the event is a separate manual action the admin also has.
    resolved = models.BooleanField(default=False, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering: ClassVar[list] = ["created_at"]
        verbose_name = "Competition report"
        constraints: ClassVar[list] = [
            # One open report per user per event: a reporter cannot pile up duplicate open reports on
            # the same event. Deleted reporters (NULL) are distinct in Postgres, so their stale
            # reports never block a new one.
            models.UniqueConstraint(
                fields=["competition", "reported_by"],
                condition=models.Q(resolved=False),
                name="uniq_open_report_per_user",
            ),
        ]
        indexes: ClassVar[list] = [models.Index(fields=["competition", "resolved"])]

    def __str__(self) -> str:
        return f"Report on {self.competition} by {self.reported_by}"
