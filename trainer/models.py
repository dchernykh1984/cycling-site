"""Virtual ride data kept on the site: finished rides (the member's records) and group rides.

The trainer page itself (static/trainer/alatau.html) owns the routes; the site stores a route only
as the key and name the page sent, so a new route or city needs no change here.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class VirtualRide(models.Model):
    """One finished ride, saved to the member's profile. Personal records are derived from these."""

    class Kind(models.TextChoices):
        RACE = "race", _("Race")
        PLAN = "plan", _("Cadence plan")
        FREE = "free", _("Free ride")

    class PowerSource(models.TextChoices):
        # Measured by a smart trainer or power meter; estimated from speed or cadence; set by hand.
        MEASURED = "measured", _("Measured power")
        ESTIMATED = "estimated", _("Estimated power")
        DEMO = "demo", _("Demo mode")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="virtual_rides")
    route = models.CharField(max_length=40, db_index=True)
    route_name = models.CharField(max_length=120, blank=True, default="")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.RACE)
    group = models.ForeignKey("GroupRide", null=True, blank=True, on_delete=models.SET_NULL, related_name="rides")
    finished_at = models.DateTimeField(default=timezone.now, db_index=True)
    duration_s = models.FloatField()
    distance_m = models.FloatField()
    elevation_gain_m = models.FloatField(default=0)
    avg_speed_kmh = models.FloatField(default=0)
    max_speed_kmh = models.FloatField(default=0)
    avg_power_w = models.PositiveIntegerField(null=True, blank=True)
    avg_cadence_rpm = models.PositiveIntegerField(null=True, blank=True)
    avg_hr_bpm = models.PositiveIntegerField(null=True, blank=True)
    max_hr_bpm = models.PositiveIntegerField(null=True, blank=True)
    power_source = models.CharField(max_length=10, choices=PowerSource.choices, default=PowerSource.ESTIMATED)
    place = models.PositiveIntegerField(null=True, blank=True)
    field_size = models.PositiveIntegerField(null=True, blank=True)
    peak_5s_w = models.PositiveIntegerField(null=True, blank=True)
    peak_1m_w = models.PositiveIntegerField(null=True, blank=True)
    peak_5m_w = models.PositiveIntegerField(null=True, blank=True)
    peak_20m_w = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-finished_at",)
        indexes = (models.Index(fields=("user", "route", "kind")),)

    def __str__(self) -> str:
        return f"{self.user_id} {self.route} {self.kind} {self.duration_s:.0f}s"


class GroupRide(models.Model):
    """A race that several members start together: one host, a route and a start time."""

    route = models.CharField(max_length=40)
    route_name = models.CharField(max_length=120, blank=True, default="")
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hosted_group_rides")
    start_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled = models.BooleanField(default=False)
    members: models.ManyToManyField = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="GroupRideMember", related_name="group_rides"
    )

    class Meta:
        ordering = ("start_at",)

    def __str__(self) -> str:
        return f"{self.route} at {self.start_at:%Y-%m-%d %H:%M}"


class GroupRideMember(models.Model):
    group = models.ForeignKey(GroupRide, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_ride_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (models.UniqueConstraint(fields=("group", "user"), name="unique_group_ride_member"),)

    def __str__(self) -> str:
        return f"{self.user_id} in {self.group_id}"


class LiveRider(models.Model):
    """What a member is doing on the trainer page right now: one row each, refreshed every second or so.

    Riders poll the site with their own position and get the others back; a row that has not been
    refreshed for ``trainer.live.ONLINE_SECONDS`` is treated as gone.
    """

    class Status(models.TextChoices):
        LOBBY = "lobby", _("Setting up a ride")
        RIDE = "ride", _("Riding")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_ride")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.LOBBY)
    route = models.CharField(max_length=40, blank=True, default="")
    mode = models.CharField(max_length=10, choices=VirtualRide.Kind.choices, default=VirtualRide.Kind.RACE)
    group = models.ForeignKey(GroupRide, null=True, blank=True, on_delete=models.SET_NULL, related_name="live_riders")
    distance_m = models.FloatField(default=0)
    speed_ms = models.FloatField(default=0)
    cadence_rpm = models.PositiveIntegerField(default=0)
    power_w = models.PositiveIntegerField(default=0)
    lane_m = models.FloatField(default=2)
    finished_s = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self) -> str:
        return f"{self.user_id} {self.status} {self.route}"
