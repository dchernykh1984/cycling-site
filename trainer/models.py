"""Virtual ride data kept on the site: finished rides (the member's records) and group rides.

The trainer page itself owns the routes (static/trainer/alatau/maps/, a folder per map); the site stores a
route only as the key and name the page sent, so a new route or city needs no change here.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from event_photos.models import BIB_MAX_LENGTH


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
    # The wind the ride was ridden in (0: none) and the bearing it blew from: a wind behind the rider is no record
    # of theirs, so a ride with wind sets no route record or top speed (trainer/records.py).
    wind_ms = models.FloatField(default=0)
    wind_from_deg = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("-finished_at",)
        indexes = (models.Index(fields=("user", "route", "kind")),)

    def __str__(self) -> str:
        return f"{self.user_id} {self.route} {self.kind} {self.duration_s:.0f}s"


class GroupRide(models.Model):
    """A race that several members start together: one host, a route and a start time.

    A race may belong to an event (specs/495-virtual-race): its registered riders join with bibs, ride their
    category's laps, and the site writes the race's timing into the event's timing streams (``trainer.race``).
    """

    class Mode(models.TextChoices):
        GROUP = "group", _("Group race")
        ITT = "itt", _("Individual time trial")

    route = models.CharField(max_length=40)
    route_name = models.CharField(max_length=120, blank=True, default="")
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hosted_group_rides")
    start_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled = models.BooleanField(default=False)
    # The host's wind (0: none) and the bearing it blows from: every member rides the race in it.
    wind_ms = models.FloatField(default=0)
    wind_from_deg = models.PositiveSmallIntegerField(default=0)
    members: models.ManyToManyField = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="GroupRideMember", related_name="group_rides"
    )
    # A race with protocols: its event, how it starts, and whether categories draft each other
    competition = models.ForeignKey(
        "calendar_app.Competition", null=True, blank=True, on_delete=models.SET_NULL, related_name="virtual_races"
    )
    mode = models.CharField(max_length=5, choices=Mode.choices, default=Mode.GROUP)
    group_gap_s = models.PositiveIntegerField(default=0)  # between the categories' starts in a group race
    itt_interval_s = models.PositiveIntegerField(default=30)  # between the riders' starts in a time trial
    draft_between_groups = models.BooleanField(default=True)
    # a loop: its riders ride their categories' laps; a route out and back or from A to B, once
    loop = models.BooleanField(default=True)
    # the bibs of riders who left, kept for them by their registration: {registration id: bib}
    kept_bibs = models.JSONField(default=dict, blank=True)
    # the last rider's own start, after the gaps between categories or the intervals of a time trial: the lobby lists
    # the race until a little after it, so every rider's page is there to start them
    last_start_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("start_at",)

    def __str__(self) -> str:
        return f"{self.route} at {self.start_at:%Y-%m-%d %H:%M}"


class GroupRideMember(models.Model):
    group = models.ForeignKey(GroupRide, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_ride_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
    # in a race with protocols: the rider's registration for its event and the bib they ride with
    registration = models.ForeignKey(
        "registrations.CompetitionRegistration",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="virtual_race_members",
    )
    bib = models.CharField(max_length=BIB_MAX_LENGTH, blank=True, default="")

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
    # the rider's drag area, m2, as their page reckons it: the wake they leave others depends on it
    cda = models.FloatField(default=0.32)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self) -> str:
        return f"{self.user_id} {self.status} {self.route}"


class RideTrack(models.Model):
    """Where a ride went and how, one sample a second: what its Strava activity is built from.

    Each point is ``[t_s, lat, lon, ele_m, distance_m, speed_ms, power_w, cadence_rpm, hr_bpm]``. The
    position is the trainer page's route at the rider's distance -- a place on the map, not a GPS fix.
    """

    ride = models.OneToOneField(VirtualRide, on_delete=models.CASCADE, primary_key=True, related_name="track")
    points = models.JSONField()

    def __str__(self) -> str:
        return f"track of {self.ride_id}"


class StravaConnection(models.Model):
    """A member's permission for the site to upload their virtual rides to Strava (``activity:write``).

    Signing in with Strava asks for ``read`` only and keeps no token; this is a separate grant the
    member gives on the profile, kept only while they want their rides sent. Turning it off revokes it
    at Strava and deletes the row (``trainer.strava``). Both tokens are kept sealed
    (``trainer.secret_box``): a copy of the database or a backup holds nothing that uploads to Strava.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="strava_connection")
    athlete_id = models.BigIntegerField()
    athlete_name = models.CharField(max_length=120, blank=True, default="")
    access_token = models.TextField()  # sealed
    refresh_token = models.TextField()  # sealed
    expires_at = models.DateTimeField()
    connected_at = models.DateTimeField(auto_now_add=True)
    # the member's box on the profile: off keeps the connection and sends nothing on its own (issue #471)
    send_rides = models.BooleanField(default=True)
    # not stored: set before deleting a grant Strava itself refused, which leaves nothing to revoke there
    revoked = False

    def __str__(self) -> str:
        return f"{self.user_id} -> strava {self.athlete_id}"


class StravaUpload(models.Model):
    """One ride sent to Strava: the upload Strava is processing, then the activity it became."""

    class Status(models.TextChoices):
        PROCESSING = "processing", _("Processing at Strava")
        DONE = "done", _("On Strava")
        FAILED = "failed", _("Not uploaded")

    ride = models.OneToOneField(VirtualRide, on_delete=models.CASCADE, primary_key=True, related_name="strava")
    status = models.CharField(max_length=12, choices=Status.choices)
    upload_id = models.CharField(max_length=30, blank=True, default="")
    activity_id = models.CharField(max_length=30, blank=True, default="")
    error = models.CharField(max_length=300, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.ride_id} {self.status}"

    @property
    def activity_url(self) -> str:
        return f"https://www.strava.com/activities/{self.activity_id}" if self.activity_id else ""


class IntervalsConnection(models.Model):
    """A member's intervals.icu, connected with their own API key (issue #471).

    The key is the member's to give and to regenerate at intervals.icu; it is kept sealed
    (``trainer.secret_box``), used only from the server and never shown again. Disconnecting deletes
    the row: there is nothing to revoke at intervals.icu.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="intervals_connection")
    athlete_id = models.CharField(max_length=40)
    athlete_name = models.CharField(max_length=120, blank=True, default="")
    api_key = models.TextField()  # sealed
    send_rides = models.BooleanField(default=False)
    connected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user_id} -> intervals.icu {self.athlete_id}"


class IntervalsUpload(models.Model):
    """One ride sent to intervals.icu: the activity it became, or why there is none."""

    class Status(models.TextChoices):
        DONE = "done", _("On intervals.icu")
        FAILED = "failed", _("Not uploaded")

    ride = models.OneToOneField(VirtualRide, on_delete=models.CASCADE, primary_key=True, related_name="intervals")
    status = models.CharField(max_length=12, choices=Status.choices)
    activity_id = models.CharField(max_length=40, blank=True, default="")
    error = models.CharField(max_length=300, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.ride_id} {self.status}"

    @property
    def activity_url(self) -> str:
        return f"https://intervals.icu/activities/{self.activity_id}" if self.activity_id else ""


class TrainerSettings(models.Model):
    """A member's settings on the trainer page -- height, weight, bike, trainer, plan and the rest -- kept with
    their account, so the page shows the same on every device they sign in on.

    ``data`` is the page's own object, which only the page reads. ``saved_at`` is the site's clock, in
    milliseconds, when the copy was saved: a page replaces it only if it had this copy, so no device's own
    clock decides which copy is the latest.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trainer_settings")
    data = models.JSONField(default=dict)
    saved_at = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id} trainer settings"
